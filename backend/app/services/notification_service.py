import logging
import os
import json
from datetime import datetime
from backend.app.models import IngestionJob

logger = logging.getLogger("app.services.notifications")

class NotificationService:
    NOTIFICATIONS_LOG_FILE = "./notifications_sent.log"

    @classmethod
    def _log_notification(cls, job_id: str, email_type: str, recipient: str, subject: str, body: str):
        """
        Appends mock email notifications to a log file so the operator can inspect them in the UI.
        """
        notification = {
            "timestamp": datetime.utcnow().isoformat(),
            "job_id": job_id,
            "email_type": email_type,
            "recipient": recipient,
            "subject": subject,
            "body": body
        }
        
        try:
            with open(cls.NOTIFICATIONS_LOG_FILE, "a") as f:
                f.write(json.dumps(notification) + "\n")
            logger.info(f"Mock email notification sent to {recipient}: {subject}")
        except Exception as e:
            logger.error(f"Failed to log notification: {str(e)}")

    @classmethod
    def send_success_notification(cls, job: IngestionJob):
        recipient = job.sender or "operator@company.com"
        subject = f"SUCCESS: Ingestion completed for job {job.id}"
        
        body = f"""Hello,

The automated data ingestion job has completed successfully.

Job Details:
- Job ID: {job.id}
- File Name: {job.attachment_name}
- Sheet: {job.sheet_name}
- Target Table: {job.target_database}.{job.target_table}
- Processing Mode: {job.processing_mode}
- Rows Ingested: {job.inserted_rows}
- Total Rows: {job.total_rows}
- Duration: {job.duration_ms} ms
- Timestamp: {datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")}

The ClickHouse table has been updated. You can review the details on the Ingestion Dashboard.

Regards,
Outlook Data Ingestion Bot
"""
        cls._log_notification(job.id, "SUCCESS_EMAIL", recipient, subject, body)

    @classmethod
    def send_failure_notification(cls, job: IngestionJob, error_message: str):
        recipient = job.sender or "operator@company.com"
        subject = f"FAILURE: Ingestion failed for job {job.id}"
        
        body = f"""Hello,

An automated data ingestion job failed schema validation or insertion check.
ZERO rows have been inserted into ClickHouse. The attachment has been quarantined.

Job Details:
- Job ID: {job.id}
- File Name: {job.attachment_name}
- Sheet: {job.sheet_name or "N/A"}
- Target Table: {job.target_database or "N/A"}.{job.target_table or "N/A"}
- Processing Mode: {job.processing_mode}
- Failure Cause: {error_message}
- Timestamp: {datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")}

You can inspect the validation errors and trigger a retry after fixing the template issues in the Ingestion Dashboard.

Regards,
Outlook Data Ingestion Bot
"""
        cls._log_notification(job.id, "FAILURE_EMAIL", recipient, subject, body)

    @classmethod
    def get_recent_notifications(cls) -> list:
        """
        Reads the notifications log file.
        """
        if not os.path.exists(cls.NOTIFICATIONS_LOG_FILE):
            return []
            
        notifications = []
        try:
            with open(cls.NOTIFICATIONS_LOG_FILE, "r") as f:
                for line in f:
                    if line.strip():
                        notifications.append(json.loads(line.strip()))
            # Return newest first
            return sorted(notifications, key=lambda x: x["timestamp"], reverse=True)
        except Exception as e:
            logger.error(f"Error reading notifications log: {str(e)}")
            return []
