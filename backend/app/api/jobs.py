from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Dict, Any, Optional
from backend.app.database import get_db
from backend.app.models import IngestionJob, JobStateHistory, ValidationError, AuditLog
from backend.app.schemas import IngestionJobResponse, IngestionJobDetailResponse
from backend.app.services.worker_service import WorkerService
from backend.app.api.auth import get_current_user
import os
import shutil
from backend.app.config import settings

router = APIRouter(prefix="/jobs", tags=["ingestion-jobs"])

@router.get("", response_model=List[IngestionJobResponse])
def get_jobs(
    status: Optional[str] = None,
    reconciliation_status: Optional[str] = None,
    target_table: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user)
):
    query = db.query(IngestionJob)
    if status:
        if status == "FAILED":
            query = query.filter(IngestionJob.status.in_(["FAILED", "CANCELLED"]))
        else:
            query = query.filter(IngestionJob.status == status)
    if reconciliation_status:
        query = query.filter(IngestionJob.reconciliation_status == reconciliation_status)
    if target_table:
        query = query.filter(IngestionJob.target_table == target_table)
        
    return query.order_by(IngestionJob.created_at.desc()).all()

@router.get("/overview/stats")
def get_overview_stats(db: Session = Depends(get_db), current_user: Any = Depends(get_current_user)):
    """
    Returns aggregated dashboard statistics.
    """
    total_jobs = db.query(IngestionJob).count()
    success_jobs = db.query(IngestionJob).filter(IngestionJob.status == "COMPLETED").count()
    failed_jobs = db.query(IngestionJob).filter(IngestionJob.status.in_(["FAILED", "CANCELLED"])).count()
    processing_jobs = db.query(IngestionJob).filter(
        IngestionJob.status.notin_(["COMPLETED", "FAILED", "QUARANTINED", "CANCELLED"])
    ).count()
    quarantined_jobs = db.query(IngestionJob).filter(IngestionJob.status == "QUARANTINED").count()
    
    # Reconciliation discrepancies count
    discrepancies = db.query(IngestionJob).filter(IngestionJob.reconciliation_status == "MISMATCHED").count()
    
    # Rows metrics
    total_rows = db.query(func.sum(IngestionJob.total_rows)).scalar() or 0
    inserted_rows = db.query(func.sum(IngestionJob.inserted_rows)).scalar() or 0
    
    success_rate = (success_jobs / total_jobs * 100) if total_jobs > 0 else 100.0
    
    # Top failure reasons
    failure_reasons = db.query(
        ValidationError.error_reason, 
        func.count(ValidationError.id).label("count")
    ).group_by(ValidationError.error_reason).order_by(func.count(ValidationError.id).desc()).limit(5).all()
    
    reasons_list = [{"reason": row[0], "count": row[1]} for row in failure_reasons]
    
    # Recent jobs for dashboard table
    recent_jobs = db.query(IngestionJob).order_by(IngestionJob.created_at.desc()).limit(5).all()
    recent_jobs_schemas = [IngestionJobResponse.from_orm(job) for job in recent_jobs]
    
    return {
        "total_jobs": total_jobs,
        "success_jobs": success_jobs,
        "failed_jobs": failed_jobs,
        "processing_jobs": processing_jobs,
        "quarantined_jobs": quarantined_jobs,
        "discrepancy_count": discrepancies,
        "total_rows": total_rows,
        "inserted_rows": inserted_rows,
        "success_rate": round(success_rate, 2),
        "top_failures": reasons_list,
        "recent_jobs": recent_jobs_schemas
    }

@router.get("/{job_id}", response_model=IngestionJobDetailResponse)
def get_job_detail(
    job_id: str, 
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user)
):
    job = db.query(IngestionJob).filter(IngestionJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

@router.post("/{job_id}/retry")
def retry_job(
    job_id: str, 
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user)
):
    """
    Copies a quarantined/failed file back to uploads/ and restarts the worker engine.
    """
    job = db.query(IngestionJob).filter(IngestionJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    if job.status not in ("QUARANTINED", "FAILED"):
        raise HTTPException(
            status_code=400, 
            detail=f"Only jobs in QUARANTINED or FAILED state can be retried. Current state is {job.status}."
        )
        
    # File details
    quarantine_filename = f"{job.id}_{job.attachment_name}"
    quarantine_path = os.path.join(settings.QUARANTINE_DIR, quarantine_filename)
    upload_path = os.path.join(settings.UPLOAD_DIR, job.attachment_name)
    
    # Fallback to normal upload path if quarantine file doesn't exist (maybe manual upload retry)
    if not os.path.exists(quarantine_path) and os.path.exists(upload_path):
        # We can use the existing upload path file
        pass
    elif os.path.exists(quarantine_path):
        # Copy back from quarantine to uploads
        try:
            shutil.copy2(quarantine_path, upload_path)
            # Remove quarantine file
            os.remove(quarantine_path)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to restore file from quarantine: {str(e)}")
    else:
        raise HTTPException(status_code=400, detail="Quarantined file is missing. Unable to retry.")

    # Reset job variables
    job.status = "JOB_CREATED"
    job.retry_count += 1
    job.error_summary = None
    
    # Clear old validation errors
    db.query(ValidationError).filter(ValidationError.job_id == job_id).delete()
    
    # Audit log
    audit = AuditLog(
        actor=current_user.username,
        action="RETRY_JOB",
        job_id=job.id,
        details=f"Job retry initiated (Retry #{job.retry_count}). State reset to JOB_CREATED."
    )
    db.add(audit)
    
    # Add new state history
    history = JobStateHistory(
        job_id=job_id,
        previous_state="QUARANTINED",
        new_state="JOB_CREATED",
        reason=f"Operator manually triggered retry.",
        actor=current_user.username
    )
    db.add(history)
    
    db.commit()
    db.refresh(job)
    
    # Restart processing
    WorkerService.start_ingestion_job_async(job.id)
    
    return {"message": "Job retry scheduled.", "job": job}

@router.post("/{job_id}/cancel")
def cancel_job(
    job_id: str, 
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user)
):
    job = db.query(IngestionJob).filter(IngestionJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    if job.status not in ("QUARANTINED", "FAILED", "EMAIL_RECEIVED"):
        raise HTTPException(status_code=400, detail="Only inactive or pending jobs can be cancelled.")
        
    # Transition to CANCELLED
    old_state = job.status
    job.status = "CANCELLED"
    
    # Delete quarantine file if exists
    quarantine_filename = f"{job.id}_{job.attachment_name}"
    quarantine_path = os.path.join(settings.QUARANTINE_DIR, quarantine_filename)
    if os.path.exists(quarantine_path):
        try:
            os.remove(quarantine_path)
        except Exception:
            pass
            
    # State history
    history = JobStateHistory(
        job_id=job_id,
        previous_state=old_state,
        new_state="CANCELLED",
        reason="Operator manually cancelled the job.",
        actor=current_user.username
    )
    db.add(history)
    
    # Audit
    audit = AuditLog(
        actor=current_user.username,
        action="CANCEL_JOB",
        job_id=job.id,
        details="Job cancelled by operator."
    )
    db.add(audit)
    
    db.commit()
    return {"message": "Job cancelled.", "job": job}
