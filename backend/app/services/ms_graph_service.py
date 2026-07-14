import os
import re
import uuid
import time
import logging
import datetime
import threading
import requests
from sqlalchemy.orm import Session
from backend.app.database import SessionLocal
from backend.app.models import MicrosoftCredential, IngestionJob, JobStateHistory, AuditLog, WorkflowConfig, MicrosoftAppConfig
from backend.app.services.worker_service import WorkerService
from backend.app.config import settings

logger = logging.getLogger("app.services.ms_graph")

class MSGraphService:
    _thread = None
    _stop_event = threading.Event()
    _poll_interval = 20  # check every 20 seconds when connected

    @classmethod
    def start_service(cls):
        cls._stop_event.clear()
        cls._thread = threading.Thread(target=cls._run_loop, daemon=True)
        cls._thread.start()
        logger.info("Microsoft Graph Mail Listener started.")

    @classmethod
    def stop_service(cls):
        cls._stop_event.set()
        if cls._thread:
            cls._thread.join(timeout=2)
            logger.info("Microsoft Graph Mail Listener stopped.")

    @classmethod
    def _run_loop(cls):
        while not cls._stop_event.is_set():
            try:
                cls._poll_mailbox()
            except Exception as e:
                logger.error(f"Error in MS Graph polling: {str(e)}")

            # Sleep in small steps to react quickly to shutdown events
            for _ in range(cls._poll_interval):
                if cls._stop_event.is_set():
                    break
                time.sleep(1)

    @classmethod
    def _get_active_token(cls, db: Session) -> str:
        """
        Retrieves the active MS Graph access token, refreshing it if expired.
        """
        cred = db.query(MicrosoftCredential).filter(MicrosoftCredential.is_active == True).first()
        if not cred:
            return None

        # Check expiration (with a 2-minute buffer)
        if cred.expires_at <= datetime.datetime.utcnow() + datetime.timedelta(minutes=2):
            logger.info("MS Graph Access Token expired or near expiry. Refreshing...")
            
            # Query active app config from DB
            config = db.query(MicrosoftAppConfig).filter(MicrosoftAppConfig.is_active == True).first()
            client_id = config.client_id if config else settings.MICROSOFT_CLIENT_ID
            client_secret = config.client_secret if config else settings.MICROSOFT_CLIENT_SECRET
            tenant_id = config.tenant_id if config else settings.MICROSOFT_TENANT_ID

            # If using mock keys, just simulate refresh
            if client_id == "mock-client-id-12345":
                cred.access_token = f"refreshed-mock-access-token-{uuid.uuid4().hex[:6]}"
                cred.expires_at = datetime.datetime.utcnow() + datetime.timedelta(hours=1)
                db.commit()
                return cred.access_token

            # Real OAuth refresh request
            try:
                token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
                payload = {
                    "client_id": client_id,
                    "grant_type": "refresh_token",
                    "refresh_token": cred.refresh_token,
                    "client_secret": client_secret
                }
                res = requests.post(token_url, data=payload, timeout=10)
                if res.status_code == 200:
                    data = res.json()
                    cred.access_token = data.get("access_token")
                    if data.get("refresh_token"):
                        cred.refresh_token = data.get("refresh_token")
                    expires_in = data.get("expires_in", 3600)
                    cred.expires_at = datetime.datetime.utcnow() + datetime.timedelta(seconds=expires_in)
                    db.commit()
                    logger.info("MS Graph Access Token refreshed successfully.")
                else:
                    logger.error(f"Failed to refresh MS Graph token: {res.text}")
                    return None
            except Exception as ex:
                logger.error(f"Error refreshing MS Graph token: {str(ex)}")
                return None

        return cred.access_token

    @classmethod
    def _poll_mailbox(cls):
        db = SessionLocal()
        try:
            token = cls._get_active_token(db)
            if not token:
                return # Not connected or could not retrieve token

            # Query unread messages
            # For prototype mock mode, simulate receiving an email if an active mock config has been triggered
            if settings.MICROSOFT_CLIENT_ID == "mock-client-id-12345":
                # In mock mode, we don't call Microsoft. We just check logs or simulate checking.
                return

            # Real MS Graph call
            headers = {"Authorization": f"Bearer {token}"}
            # Retrieve unread messages in the inbox
            messages_url = "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages?$filter=isRead eq false&$select=id,subject,from,receivedDateTime,hasAttachments"
            res = requests.get(messages_url, headers=headers, timeout=10)
            if res.status_code != 200:
                logger.error(f"Graph API query failed: {res.text}")
                return

            messages = res.json().get("value", [])
            for msg in messages:
                cls._process_msg(msg, headers, db)

        finally:
            db.close()

    @classmethod
    def _process_msg(cls, msg, headers, db: Session):
        msg_id = msg.get("id")
        subject = msg.get("subject", "")
        sender_info = msg.get("from", {}).get("emailAddress", {})
        sender = sender_info.get("address", "")
        received_time_str = msg.get("receivedDateTime")
        
        # Parse timestamp
        try:
            received_time = datetime.datetime.fromisoformat(received_time_str.replace("Z", "+00:00"))
        except Exception:
            received_time = datetime.datetime.utcnow()

        # Check workflow configuration rules
        workflows = db.query(WorkflowConfig).all()
        matching_config = None
        for config in workflows:
            if config.email_subject_pattern:
                if re.search(config.email_subject_pattern, subject, re.IGNORECASE):
                    matching_config = config
                    break

        if not matching_config:
            return # Doesn't match rules

        # Extract target table name from subject/body
        target_table = None
        target_database = "default"
        
        match = re.search(r"table:\s*([a-zA-Z0-9_]+)", subject, re.IGNORECASE)
        if match:
            target_table = match.group(1)

        # Get body if table not in subject
        if not target_table:
            body_url = f"https://graph.microsoft.com/v1.0/me/messages/{msg_id}?$select=body"
            body_res = requests.get(body_url, headers=headers, timeout=10)
            if body_res.status_code == 200:
                body_content = body_res.json().get("body", {}).get("content", "")
                match_body = re.search(r"table:\s*([a-zA-Z0-9_]+)", body_content, re.IGNORECASE)
                if match_body:
                    target_table = match_body.group(1)
                match_db = re.search(r"database:\s*([a-zA-Z0-9_]+)", body_content, re.IGNORECASE)
                if match_db:
                    target_database = match_db.group(1)

        if not target_table:
            return # Table target missing

        # Fetch attachments
        attachments_url = f"https://graph.microsoft.com/v1.0/me/messages/{msg_id}/attachments"
        att_res = requests.get(attachments_url, headers=headers, timeout=10)
        if att_res.status_code != 200:
            return

        attachments = att_res.json().get("value", [])
        has_xlsx = False
        for att in attachments:
            name = att.get("name", "")
            # Verify Excel workbook
            if name.endswith(".xlsx") or name.endswith(".xlsm"):
                has_xlsx = True
                
                # Fetch full attachment details with contentBytes
                att_detail_url = f"https://graph.microsoft.com/v1.0/me/messages/{msg_id}/attachments/{att.get('id')}"
                att_detail_res = requests.get(att_detail_url, headers=headers, timeout=10)
                if att_detail_res.status_code != 200:
                    continue
                    
                import base64
                content_bytes_b64 = att_detail_res.json().get("contentBytes")
                if not content_bytes_b64:
                    continue
                    
                attachment_bytes = base64.b64decode(content_bytes_b64)
                job_id = f"job_msgraph_{uuid.uuid4().hex[:10]}"
                file_path = os.path.join(settings.UPLOAD_DIR, name)
                
                # Save attachment locally
                with open(file_path, "wb") as f:
                    f.write(attachment_bytes)

                # Register job
                job = IngestionJob(
                    id=job_id,
                    correlation_id=f"msgraph_api_{uuid.uuid4().hex[:8]}",
                    email_id=msg_id,
                    sender=sender,
                    subject=subject,
                    received_time=received_time,
                    attachment_name=name,
                    attachment_size=len(attachment_bytes),
                    target_database=target_database,
                    target_table=target_table,
                    sheet_name=None,
                    status="EMAIL_RECEIVED",
                    processing_mode=matching_config.mode,
                    retry_count=0,
                    reconciliation_status="PENDING"
                )
                db.add(job)
                db.commit()

                # Save history
                h1 = JobStateHistory(
                    job_id=job_id, previous_state=None, new_state="EMAIL_RECEIVED",
                    reason="Microsoft Graph API detected incoming email.", actor="msgraph_poller"
                )
                h2 = JobStateHistory(
                    job_id=job_id, previous_state="EMAIL_RECEIVED", new_state="ATTACHMENT_RECEIVED",
                    reason=f"Graph API successfully downloaded attachment '{name}'.", actor="msgraph_poller"
                )
                db.add_all([h1, h2])
                
                # Audit
                audit = AuditLog(
                    actor="msgraph_poller", action="MS_GRAPH_TRIGGERED", job_id=job_id,
                    details=f"Read message '{subject}' from '{sender}'. Processing attachment '{name}'."
                )
                db.add(audit)
                
                job.status = "JOB_CREATED"
                db.commit()

                logger.info(f"MSGraph Service: Ingestion job {job_id} successfully created.")
                
                # Start job asynchronously
                WorkerService.start_ingestion_job_async(job_id)
                break # Only process first matching spreadsheet

        # Mark email as read in Outlook mailbox
        if has_xlsx:
            patch_url = f"https://graph.microsoft.com/v1.0/me/messages/{msg_id}"
            requests.patch(patch_url, headers=headers, json={"isRead": True}, timeout=10)
            logger.info("MSGraph Service: Message marked as Read in mailbox.")
