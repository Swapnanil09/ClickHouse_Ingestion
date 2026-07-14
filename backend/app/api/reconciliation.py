from fastapi import APIRouter, Depends, HTTPException, Header, status
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any
from backend.app.database import get_db
from backend.app.models import ReconciliationRun, IngestionJob, AuditLog
from backend.app.schemas import PowerAutomateReconcileRequest, ReconciliationRunResponse
from backend.app.services.reconciliation_service import ReconciliationService
from backend.app.api.upload import verify_api_key
from backend.app.api.auth import get_current_user

router = APIRouter(prefix="/reconciliation", tags=["power-automate-reconciliation"])

@router.post("", response_model=ReconciliationRunResponse)
def reconcile_job(
    payload: PowerAutomateReconcileRequest,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key)
):
    """
    Webhook called by Power Automate after processing finishes to check row count & parameter matching.
    """
    try:
        run = ReconciliationService.run_reconciliation(
            db=db,
            job_id=payload.ingestion_job_id,
            email_id=payload.email_id,
            attachment_hash=payload.attachment_hash,
            target_database=payload.target_database,
            target_table=payload.target_table,
            expected_row_count=payload.expected_row_count
        )
        return run
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reconciliation error: {str(e)}")

@router.get("/runs", response_model=List[ReconciliationRunResponse])
def get_reconciliation_runs(
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user)
):
    return db.query(ReconciliationRun).order_by(ReconciliationRun.run_timestamp.desc()).all()

@router.get("/discrepancies", response_model=List[ReconciliationRunResponse])
def get_discrepancies(
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user)
):
    """
    Lists only runs that detected a discrepancy (mismatch).
    """
    return db.query(ReconciliationRun).filter(
        ReconciliationRun.match_status == "MISMATCHED"
    ).order_by(ReconciliationRun.run_timestamp.desc()).all()
