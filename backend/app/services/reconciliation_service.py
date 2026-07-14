import logging
from sqlalchemy.orm import Session
from backend.app.models import IngestionJob, ReconciliationRun, AuditLog

logger = logging.getLogger("app.services.reconciliation")

class ReconciliationService:
    
    @classmethod
    def run_reconciliation(
        cls, 
        db: Session, 
        job_id: str, 
        email_id: str, 
        attachment_hash: str, 
        target_database: str, 
        target_table: str, 
        expected_row_count: int
    ) -> ReconciliationRun:
        """
        Executes reconciliation validation sent by Power Automate.
        Compares metadata and counts, updates the job reconciliation status.
        """
        job = db.query(IngestionJob).filter(IngestionJob.id == job_id).first()
        if not job:
            raise ValueError(f"Job {job_id} not found for reconciliation.")
            
        mismatches = []
        
        # 1. Compare email message ID
        if job.email_id != email_id:
            mismatches.append(f"Email ID mismatch: PA expects '{email_id}', backend has '{job.email_id}'.")
            
        # 2. Compare attachment hash
        if job.attachment_hash != attachment_hash:
            mismatches.append(f"Attachment hash mismatch: PA has '{attachment_hash}', backend has '{job.attachment_hash}'.")
            
        # 3. Compare database & table
        if job.target_database.lower() != target_database.lower():
            mismatches.append(f"Database mismatch: PA expects '{target_database}', backend used '{job.target_database}'.")
        if job.target_table.lower() != target_table.lower():
            mismatches.append(f"Table mismatch: PA expects '{target_table}', backend used '{job.target_table}'.")
            
        # 4. Compare row count
        # For failed jobs, backend inserted rows is 0. PA might expect the excel count.
        # Let's check matching based on what was actually inserted.
        if job.inserted_rows != expected_row_count:
            mismatches.append(f"Row count mismatch: PA expects {expected_row_count} rows, backend inserted {job.inserted_rows} rows.")
            
        # Determine status
        match_status = "MATCHED"
        discrepancy_details = None
        
        if mismatches:
            match_status = "MISMATCHED"
            discrepancy_details = "\n".join(mismatches)
            job.reconciliation_status = "MISMATCHED"
            logger.warning(f"Reconciliation Mismatch detected for Job {job_id}:\n{discrepancy_details}")
            
            # Log audit
            audit = AuditLog(
                actor="power_automate",
                action="RECONCILIATION_FAILED",
                job_id=job.id,
                details=f"Discrepancies: {discrepancy_details}"
            )
            db.add(audit)
        else:
            job.reconciliation_status = "MATCHED"
            logger.info(f"Reconciliation Matched successfully for Job {job_id}.")
            
            # Log audit
            audit = AuditLog(
                actor="power_automate",
                action="RECONCILIATION_SUCCESS",
                job_id=job.id,
                details="Reconciliation details matched perfectly."
            )
            db.add(audit)
            
        db.commit()
        
        # Save run record
        run = ReconciliationRun(
            job_id=job_id,
            email_id=email_id,
            attachment_hash=attachment_hash,
            target_database=target_database,
            target_table=target_table,
            backend_row_count=job.inserted_rows,
            pa_row_count=expected_row_count,
            match_status=match_status,
            discrepancy_details=discrepancy_details
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        
        return run

    @classmethod
    def run_auto_reconciliation(cls, db: Session, job: IngestionJob):
        """
        Auto reconciliation triggered on job completion as an internal check.
        """
        # If the job failed or was quarantined, they will mismatched with PA's expected total rows
        # unless PA is aware of the failure.
        # This auto check sets up an initial reconciliation state.
        if job.status == "FAILED":
            job.reconciliation_status = "PENDING"
        else:
            job.reconciliation_status = "PENDING"
        db.commit()
