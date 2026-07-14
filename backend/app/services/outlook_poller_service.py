import imaplib
import email
from email.header import decode_header
import os
import re
import uuid
import time
import logging
import datetime
import threading
from sqlalchemy.orm import Session
from backend.app.database import SessionLocal
from backend.app.models import IngestionJob, JobStateHistory, AuditLog, WorkflowConfig
from backend.app.services.worker_service import WorkerService
from backend.app.config import settings

logger = logging.getLogger("app.services.outlook_poller")

class OutlookPollerService:
    _poller_thread = None
    _stop_event = threading.Event()

    @classmethod
    def start_poller(cls):
        """
        Starts the background email polling thread if interval is configured.
        """
        if settings.OUTLOOK_POLL_INTERVAL_SECS <= 0:
            logger.info("Outlook Direct Poller is disabled (OUTLOOK_POLL_INTERVAL_SECS <= 0).")
            return
            
        if not settings.OUTLOOK_EMAIL or not settings.OUTLOOK_PASSWORD:
            logger.warning("Outlook credentials are not configured. Direct Poller cannot start.")
            return

        cls._stop_event.clear()
        cls._poller_thread = threading.Thread(target=cls._polling_loop, daemon=True)
        cls._poller_thread.start()
        logger.info(f"Outlook Direct Poller started. Checking every {settings.OUTLOOK_POLL_INTERVAL_SECS} seconds.")

    @classmethod
    def stop_poller(cls):
        cls._stop_event.set()
        if cls._poller_thread:
            cls._poller_thread.join(timeout=2)
            logger.info("Outlook Direct Poller stopped.")

    @classmethod
    def _polling_loop(cls):
        while not cls._stop_event.is_set():
            try:
                cls._check_outlook_mailbox()
            except Exception as e:
                logger.error(f"Error in Outlook mailbox polling execution: {str(e)}")
                
            # Sleep for the configured interval, checking for stop event
            for _ in range(settings.OUTLOOK_POLL_INTERVAL_SECS):
                if cls._stop_event.is_set():
                    break
                time.sleep(1)

    @classmethod
    def _check_outlook_mailbox(cls):
        logger.info("Direct Poller: Connecting to Outlook IMAP server...")
        try:
            mail = imaplib.IMAP4_SSL(settings.OUTLOOK_IMAP_SERVER, settings.OUTLOOK_IMAP_PORT)
            mail.login(settings.OUTLOOK_EMAIL, settings.OUTLOOK_PASSWORD)
            mail.select("inbox")
            
            # Search for unread messages
            status, messages = mail.search(None, "UNSEEN")
            if status != "OK" or not messages[0]:
                mail.logout()
                return
                
            mail_ids = messages[0].split()
            logger.info(f"Direct Poller: Found {len(mail_ids)} unread email(s).")
            
            db = SessionLocal()
            try:
                for mail_id in mail_ids:
                    cls._process_email(mail, mail_id, db)
            finally:
                db.close()
                
            mail.close()
            mail.logout()
        except Exception as e:
            logger.error(f"IMAP connection or parsing failed: {str(e)}")

    @classmethod
    def _process_email(cls, mail, mail_id, db: Session):
        # Fetch the email body and headers
        res, msg_data = mail.fetch(mail_id, "(RFC822)")
        if res != "OK":
            return
            
        raw_email = msg_data[0][1]
        msg = email.message_from_bytes(raw_email)
        
        # Decode subject
        subject, encoding = decode_header(msg["Subject"])[0]
        if isinstance(subject, bytes):
            subject = subject.decode(encoding or "utf-8", errors="ignore")
            
        # Decode sender
        sender = msg.get("From", "")
        
        logger.info(f"Direct Poller: Inspecting email '{subject}' from '{sender}'")
        
        # Match subject configuration rules
        # Fetch workflows
        workflows = db.query(WorkflowConfig).all()
        matching_config = None
        for config in workflows:
            if config.email_subject_pattern:
                if re.search(config.email_subject_pattern, subject, re.IGNORECASE):
                    matching_config = config
                    break
                    
        if not matching_config:
            logger.info(f"Direct Poller: Email subject '{subject}' did not match any active routing rules. Skipping.")
            return

        # Extract target table name from subject/body using rules
        target_table = None
        target_database = "default"
        
        # Attempt extraction from subject
        # Look for table: user_activities or similar
        match = re.search(r"table:\s*([a-zA-Z0-9_]+)", subject, re.IGNORECASE)
        if match:
            target_table = match.group(1)
            
        # If not in subject, try reading email text body
        if not target_table:
            body_text = ""
            if msg.is_multipart():
                for part in msg.walk():
                    content_type = part.get_content_type()
                    content_disposition = str(part.get("Content-Disposition"))
                    if content_type == "text/plain" and "attachment" not in content_disposition:
                        body_text = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                        break
            else:
                body_text = msg.get_payload(decode=True).decode("utf-8", errors="ignore")
                
            match_body = re.search(r"table:\s*([a-zA-Z0-9_]+)", body_text, re.IGNORECASE)
            if match_body:
                target_table = match_body.group(1)
                
            match_db = re.search(r"database:\s*([a-zA-Z0-9_]+)", body_text, re.IGNORECASE)
            if match_db:
                target_database = match_db.group(1)

        if not target_table:
            logger.warning(f"Direct Poller: Matched subject but could not extract target ClickHouse table name from body or subject. Skipping.")
            return

        # Process attachments
        has_xlsx = False
        for part in msg.walk():
            content_disposition = str(part.get("Content-Disposition"))
            if "attachment" in content_disposition:
                filename = part.get_filename()
                if filename and (filename.endswith(".xlsx") or filename.endswith(".xlsm")):
                    # Found target Excel workbook!
                    has_xlsx = True
                    attachment_bytes = part.get_payload(decode=True)
                    
                    job_id = f"job_direct_{uuid.uuid4().hex[:10]}"
                    file_path = os.path.join(settings.UPLOAD_DIR, filename)
                    
                    # Save Excel file
                    with open(file_path, "wb") as f:
                        f.write(attachment_bytes)
                        
                    # Create job
                    job = IngestionJob(
                        id=job_id,
                        correlation_id=f"direct_imap_{uuid.uuid4().hex[:8]}",
                        email_id=msg.get("Message-ID", f"direct_imap_msg_{uuid.uuid4().hex[:8]}"),
                        sender=sender,
                        subject=subject,
                        received_time=datetime.datetime.utcnow(),
                        attachment_name=filename,
                        attachment_size=len(attachment_bytes),
                        target_database=target_database,
                        target_table=target_table,
                        sheet_name=None, # Process first sheet by default
                        status="EMAIL_RECEIVED",
                        processing_mode=matching_config.mode,
                        retry_count=0,
                        reconciliation_status="PENDING"
                    )
                    db.add(job)
                    db.commit()
                    
                    # Timeline logging
                    h1 = JobStateHistory(
                        job_id=job_id, previous_state=None, new_state="EMAIL_RECEIVED",
                        reason="Direct IMAP Poller fetched email from Inbox.", actor="direct_imap_poller"
                    )
                    h2 = JobStateHistory(
                        job_id=job_id, previous_state="EMAIL_RECEIVED", new_state="ATTACHMENT_RECEIVED",
                        reason=f"Excel attachment '{filename}' saved locally.", actor="direct_imap_poller"
                    )
                    h3 = JobStateHistory(
                        job_id=job_id, previous_state="ATTACHMENT_RECEIVED", new_state="JOB_CREATED",
                        reason="Direct Job created. Forwarding to pipeline validation runner.", actor="direct_imap_poller"
                    )
                    db.add_all([h1, h2, h3])
                    
                    # Audit
                    audit = AuditLog(
                        actor="direct_imap_poller",
                        action="IMAP_TRIGGERED",
                        job_id=job_id,
                        details=f"Retrieved and matched email '{subject}' with excel attachment '{filename}'."
                    )
                    db.add(audit)
                    
                    job.status = "JOB_CREATED"
                    db.commit()
                    
                    logger.info(f"Direct Poller: Ingestion job {job_id} scheduled.")
                    
                    # Start async ingestion pipeline
                    WorkerService.start_ingestion_job_async(job_id)
                    break # Process one attachment per email for now
                    
        # Mark email as read/seen and save changes
        if has_xlsx:
            mail.store(mail_id, "+FLAGS", "\\Seen")
            logger.info("Direct Poller: Marked processed email as Seen.")
