from fastapi import APIRouter, Depends, HTTPException, Header, status
from sqlalchemy.orm import Session
from typing import Optional, Dict, Any, List
import uuid
import base64
import os
import datetime
from backend.app.database import get_db
from backend.app.models import IngestionJob, JobStateHistory, AuditLog
from backend.app.schemas import PowerAutomateIngestRequest, IngestionJobResponse
from backend.app.services.worker_service import WorkerService
from backend.app.services.notification_service import NotificationService
from backend.app.config import settings
from backend.app.api.auth import get_current_user

router = APIRouter(prefix="/upload", tags=["ingestion-trigger"])

def verify_api_key(x_api_key: Optional[str] = Header(None)):
    """
    Secures webhook endpoints. Power Automate must supply X-API-KEY.
    """
    if settings.POWER_AUTOMATE_API_KEY:
        if not x_api_key or x_api_key != settings.POWER_AUTOMATE_API_KEY:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="POWER_AUTOMATE_AUTH_FAILED: Invalid or missing X-API-KEY header."
            )
    return x_api_key

@router.post("/webhook", response_model=IngestionJobResponse, status_code=202)
def power_automate_webhook(
    payload: PowerAutomateIngestRequest,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key)
):
    """
    API endpoint called by Microsoft Power Automate when an email with attachment is received.
    Decodes file content, saves to disk, creates IngestionJob, and starts background execution.
    """
    # 1. Generate unique Job ID and correlation ID
    job_id = f"job_{uuid.uuid4().hex[:12]}"
    correlation_id = payload.workflow_run_id or f"corr_{uuid.uuid4().hex[:12]}"
    
    # 2. Decode base64 attachment and write to uploads/
    try:
        file_bytes = base64.b64decode(payload.file_content_base64)
        file_path = os.path.join(settings.UPLOAD_DIR, payload.attachment_name)
        
        with open(file_path, "wb") as f:
            f.write(file_bytes)
            
        file_size = len(file_bytes)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"EXCEL_INVALID: Failed to decode or save file attachment. Detail: {str(e)}"
        )
        
    # 3. Create Ingestion Job Record
    # Set status to EMAIL_RECEIVED, then transition to ATTACHMENT_RECEIVED, then JOB_CREATED
    job = IngestionJob(
        id=job_id,
        correlation_id=correlation_id,
        email_id=payload.email_id,
        sender=payload.sender,
        subject=payload.subject,
        received_time=datetime.datetime.fromisoformat(payload.received_time.replace("Z", "+00:00")),
        attachment_name=payload.attachment_name,
        attachment_size=file_size,
        target_database=payload.target_database or "AUTO",
        target_table=payload.target_table,
        sheet_name=payload.sheet_name,
        status="EMAIL_RECEIVED",
        processing_mode=payload.processing_mode or "STRICT",
        retry_count=0,
        reconciliation_status="PENDING"
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    
    # Write initial history
    history1 = JobStateHistory(
        job_id=job_id, previous_state=None, new_state="EMAIL_RECEIVED", 
        reason="Power Automate workflow detected incoming Outlook email.", actor="power_automate"
    )
    history2 = JobStateHistory(
        job_id=job_id, previous_state="EMAIL_RECEIVED", new_state="ATTACHMENT_RECEIVED", 
        reason=f"Excel attachment '{payload.attachment_name}' downloaded and saved.", actor="power_automate"
    )
    history3 = JobStateHistory(
        job_id=job_id, previous_state="ATTACHMENT_RECEIVED", new_state="JOB_CREATED", 
        reason="Job created and queued for asynchronous profiling & validation.", actor="system"
    )
    db.add_all([history1, history2, history3])
    
    # Audit log
    audit = AuditLog(
        actor="power_automate",
        action="WEBHOOK_TRIGGERED",
        job_id=job_id,
        details=f"Received upload request for table '{payload.target_table}' from sender '{payload.sender}'"
    )
    db.add(audit)
    
    # Update job state variable
    job.status = "JOB_CREATED"
    db.commit()
    db.refresh(job)
    
    # 4. Trigger asynchronous processing
    WorkerService.start_ingestion_job_async(job_id)
    
    return job

@router.get("/notifications", response_model=List[Dict[str, Any]])
def get_sent_notifications(current_user: Any = Depends(get_current_user)):
    """
    Returns mock email notifications sent by the system (for inspection in the dashboard).
    """
    return NotificationService.get_recent_notifications()

@router.post("/simulate", response_model=IngestionJobResponse)
def simulate_power_automate_flow(
    simulation_in: Dict[str, Any],
    db: Session = Depends(get_db)
):
    """
    Developer utility endpoint to mock the Power Automate flow by writing a custom Excel sheet
    on-the-fly and sending it to our own webhook.
    """
    preset = simulation_in.get("preset_name", "success")
    table = simulation_in.get("target_table", "user_activities")
    database = simulation_in.get("target_database", "default")
    mode = simulation_in.get("processing_mode", "STRICT")
    sheet_name = simulation_in.get("sheet_name", "Sheet1")
    
    # Import openpyxl to build the workbook
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_name
    
    # Build data sheets based on preset
    if preset == "success":
        # Table schema: id (UInt32), user_id (String), activity (String), timestamp (DateTime)
        ws.append(["id", "user_id", "activity", "timestamp"])
        ws.append([101, "usr_alice", "login", "2026-07-14 14:00:00"])
        ws.append([102, "usr_bob", "view_dashboard", "2026-07-14 14:05:00"])
        ws.append([103, "usr_charlie", "export_report", "2026-07-14 14:10:00"])
    elif preset == "missing_column":
        # Required 'user_id' is missing
        ws.append(["id", "activity", "timestamp"])
        ws.append([104, "login", "2026-07-14 14:15:00"])
    elif preset == "unexpected_column":
        # 'bonus_points' is unexpected in STRICT mode
        ws.append(["id", "user_id", "activity", "timestamp", "bonus_points"])
        ws.append([105, "usr_diana", "login", "2026-07-14 14:20:00", 50])
    elif preset == "type_error":
        # Row 2 contains 'abc' which is not a valid UInt32 id
        ws.append(["id", "user_id", "activity", "timestamp"])
        ws.append([106, "usr_edward", "login", "2026-07-14 14:25:00"])
        ws.append(["abc", "usr_fiona", "login", "2026-07-14 14:30:00"])  # Error row!
    else:
        # Default simple table
        ws.append(["id", "user_id", "activity", "timestamp"])
        ws.append([201, "usr_test", "test", "2026-07-14 14:35:00"])
        
    # Write workbook to temp file, then encode base64
    temp_filename = f"sim_{uuid.uuid4().hex[:8]}.xlsx"
    temp_path = os.path.join(settings.UPLOAD_DIR, temp_filename)
    wb.save(temp_path)
    wb.close()
    
    with open(temp_path, "rb") as f:
        file_bytes = f.read()
    file_b64 = base64.b64encode(file_bytes).decode("utf-8")
    
    # Clean up temp file
    if os.path.exists(temp_path):
        os.remove(temp_path)
        
    # Form Webhook request payload
    req = PowerAutomateIngestRequest(
        email_id=f"msg-{uuid.uuid4().hex[:10]}",
        sender="outlook-power-automate@company.com",
        subject=f"SIMULATED FLOW: upload_request for table: {table}",
        received_time=datetime.datetime.utcnow().isoformat() + "Z",
        attachment_name=f"simulated_attachment_{preset}.xlsx",
        file_content_base64=file_b64,
        workflow_run_id=f"run-{uuid.uuid4().hex[:12]}",
        target_table=table,
        target_database=database,
        processing_mode=mode,
        sheet_name=sheet_name
    )
    
    # Call webhook directly (bypass HTTP layer for simulation test)
    # Using settings api key
    return power_automate_webhook(
        payload=req,
        db=db,
        api_key=settings.POWER_AUTOMATE_API_KEY
    )

