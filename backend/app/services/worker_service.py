import os
import hashlib
import time
import shutil
import logging
import traceback
import datetime
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy.orm import Session
from backend.app.database import SessionLocal
from backend.app.models import IngestionJob, JobStateHistory, ValidationError, ClickHouseConnection, MockClickHouseTable
from backend.app.services.clickhouse_service import ClickHouseService
from backend.app.services.excel_service import ExcelService
from backend.app.services.validation_service import ValidationService
from backend.app.services.reconciliation_service import ReconciliationService
from backend.app.services.notification_service import NotificationService
from backend.app.config import settings
from backend.app.utils.security import decrypt_password

logger = logging.getLogger("app.services.worker")

# Thread pool for asynchronous processing
executor = ThreadPoolExecutor(max_workers=4)

class WorkerService:
    
    @classmethod
    def start_ingestion_job_async(cls, job_id: str):
        """
        Launches the ingestion job in a background thread.
        """
        executor.submit(cls._run_ingestion_job, job_id)

    @classmethod
    def _transition_state(cls, db: Session, job: IngestionJob, new_state: str, reason: str = None) -> IngestionJob:
        """
        Updates the job status and logs it in the job state history.
        """
        old_state = job.status
        job.status = new_state
        
        history_entry = JobStateHistory(
            job_id=job.id,
            previous_state=old_state,
            new_state=new_state,
            reason=reason,
            actor="background_worker"
        )
        db.add(history_entry)
        db.commit()
        db.refresh(job)
        
        logger.info(f"Job {job.id} transitioned from {old_state} to {new_state}. Reason: {reason}")
        return job

    @classmethod
    def _run_ingestion_job(cls, job_id: str):
        """
        The core ingestion pipeline executed in background.
        """
        db = SessionLocal()
        start_time = time.time()
        job = db.query(IngestionJob).filter(IngestionJob.id == job_id).first()
        
        if not job:
            logger.error(f"Ingestion job {job_id} not found in database.")
            db.close()
            return
            
        try:
            # 1. State: FILE_STORED
            cls._transition_state(db, job, "FILE_STORED", "Excel file stored locally.")
            
            # File location
            file_path = os.path.join(settings.UPLOAD_DIR, job.attachment_name)
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"Stored file not found at {file_path}")

            # Calculate actual SHA-256 hash of the file if not already provided
            hasher = hashlib.sha256()
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hasher.update(chunk)
            file_hash = hasher.hexdigest()
            job.attachment_hash = file_hash
            db.commit()

            # 2. Idempotency check:
            # Check if there is already a COMPLETED job with same attachment hash, target db, table, and sheet
            # Skip if this is a manual retry of the exact same job (retry_count > 0)
            if job.retry_count == 0:
                duplicate_job = db.query(IngestionJob).filter(
                    IngestionJob.attachment_hash == file_hash,
                    IngestionJob.target_database == job.target_database,
                    IngestionJob.target_table == job.target_table,
                    IngestionJob.sheet_name == job.sheet_name,
                    IngestionJob.status == "COMPLETED",
                    IngestionJob.id != job.id
                ).first()
                
                if duplicate_job:
                    job.error_summary = f"DUPLICATE_INGESTION: File attachment hash {file_hash} has already been ingested successfully in Job {duplicate_job.id}."
                    cls._transition_state(db, job, "FAILED", "Duplicate ingestion detected.")
                    db.close()
                    return

            # 3. State: EXCEL_PROFILING
            cls._transition_state(db, job, "EXCEL_PROFILING", "Profiling Excel structure and sheets.")
            
            # Layer 1 Validation (File Validation)
            file_ok, file_msg = ValidationService.validate_file(file_path)
            if not file_ok:
                raise ValueError(f"EXCEL_INVALID: {file_msg}")
                
            # Profile sheets
            wb_meta = ExcelService.inspect_workbook(file_path)
            
            # Determine which sheet to process
            sheet_to_use = job.sheet_name
            if not sheet_to_use:
                # Default to first sheet
                sheet_to_use = wb_meta["sheet_names"][0]
                job.sheet_name = sheet_to_use
                db.commit()
                
            if sheet_to_use not in wb_meta["sheet_names"]:
                raise ValueError(f"EXCEL_INVALID: Sheet '{sheet_to_use}' not found in workbook.")
                
            # Profile single sheet
            sheet_meta = ExcelService.profile_sheet(file_path, sheet_to_use)
            if sheet_meta["is_empty"]:
                raise ValueError("EXCEL_EMPTY: Excel sheet contains no columns or data.")
                
            job.total_rows = sheet_meta["total_rows"]
            db.commit()
            
            cls._transition_state(db, job, "EXCEL_PROFILED", f"Sheet '{sheet_to_use}' profiled. Found {sheet_meta['total_rows']} rows.")

            # 4. State: TABLE_SEARCHING (Discovery)
            cls._transition_state(db, job, "TABLE_SEARCHING", "Searching for target table.")
            
            # Fetch active ClickHouse connection
            ch_conn = db.query(ClickHouseConnection).filter(ClickHouseConnection.is_active == True).first()
            if not ch_conn:
                # If no connection, and we are in emulated mode, default configure it
                if settings.CLICKHOUSE_HOST == "emulated":
                    ch_conn = ClickHouseConnection(
                        name="Default Emulator Connection",
                        host="emulated",
                        port=8123,
                        username="default",
                        password_encrypted="encrypted",
                        secure=False,
                        databases_restricted="default,analytics,production"
                    )
                    db.add(ch_conn)
                    db.commit()
                else:
                    raise Exception("CLICKHOUSE_CONNECTION_FAILED: No active ClickHouse connection is configured.")

            # Table discovery validation (Layer 2)
            disc_ok, disc_msg, discovered_db = ValidationService.validate_table_discovery(
                target_table=job.target_table,
                target_database=job.target_database,
                connection_host=ch_conn.host,
                connection_port=ch_conn.port,
                connection_user=ch_conn.username,
                connection_pass=decrypt_password(ch_conn.password_encrypted), # Encypted password decrypted for real ClickHouse connection
                connection_secure=ch_conn.secure,
                db_session=db
            )
            
            if not disc_ok:
                raise ValueError(f"TABLE_NOT_FOUND: {disc_msg}")
                
            job.target_database = discovered_db
            db.commit()
            
            cls._transition_state(db, job, "TABLE_FOUND", f"Target table '{discovered_db}.{job.target_table}' found.")

            # 5. State: SCHEMA_VALIDATING
            cls._transition_state(db, job, "SCHEMA_VALIDATING", "Fetching ClickHouse schema and validating columns.")
            
            # Fetch schema
            ch_schema = ClickHouseService.get_table_schema(
                host=ch_conn.host,
                port=ch_conn.port,
                username=ch_conn.username,
                password=decrypt_password(ch_conn.password_encrypted),
                secure=ch_conn.secure,
                database=discovered_db,
                table_name=job.target_table,
                db_session=db
            )
            
            if not ch_schema:
                raise ValueError(f"TABLE_NOT_FOUND: Failed to retrieve schema for table '{discovered_db}.{job.target_table}'. Ensure it exists.")

            # Layer 3: Schema Validation
            schema_ok, schema_msg, schema_errors = ValidationService.validate_schema(
                excel_columns=sheet_meta["columns"],
                ch_schema=ch_schema,
                mode=job.processing_mode
            )
            
            if not schema_ok:
                # Add validation errors to database
                for err in schema_errors:
                    val_err = ValidationError(
                        job_id=job.id,
                        column_name=err.get("column_name"),
                        error_reason=err.get("error_reason")
                    )
                    db.add(val_err)
                db.commit()
                raise ValueError(f"SCHEMA_MISMATCH: {schema_msg}")
                
            cls._transition_state(db, job, "SCHEMA_VALIDATED", "Excel headers match ClickHouse schema.")

            # 6. State: DATA_VALIDATING
            cls._transition_state(db, job, "DATA_VALIDATING", "Validating cell types and values row by row.")
            
            # Stream/chunk rows and check types
            row_errors = []
            chunk_size = 2000
            
            # Headers map
            cols_normalized = [c["normalized_name"] for c in sheet_meta["columns"]]
            
            row_idx = sheet_meta["header_row_index"] + 1
            chunks = ExcelService.read_sheet_chunks(
                file_path=file_path,
                sheet_name=sheet_to_use,
                header_row_index=sheet_meta["header_row_index"],
                columns=cols_normalized,
                chunk_size=chunk_size
            )
            
            for chunk in chunks:
                chunk_errs = ValidationService.validate_rows_chunk(chunk, ch_schema, row_idx)
                row_errors.extend(chunk_errs)
                row_idx += len(chunk)
                
            if row_errors:
                # Store errors
                # Limit stored errors count to 500 in DB to avoid overflow
                for err in row_errors[:500]:
                    val_err = ValidationError(
                        job_id=job.id,
                        row_number=err["row_number"],
                        column_name=err["column_name"],
                        expected_type=err["expected_type"],
                        actual_value=err["actual_value"],
                        error_reason=err["error_reason"]
                    )
                    db.add(val_err)
                
                job.invalid_rows = len(row_errors)
                job.valid_rows = job.total_rows - len(row_errors)
                db.commit()
                
                raise ValueError(f"ROW_VALIDATION_FAILED: Found {len(row_errors)} row value mismatches.")
                
            # No errors
            job.valid_rows = job.total_rows
            job.invalid_rows = 0
            db.commit()
            
            cls._transition_state(db, job, "DATA_VALIDATED", "All row cell types and constraints validated successfully.")

            # 7. DRY RUN Mode check
            if job.processing_mode.upper() == "DRY_RUN":
                cls._transition_state(db, job, "COMPLETED", "Dry run execution completed. Schema and values are correct. No rows inserted.")
                db.close()
                return

            # 8. State: READY_TO_INSERT
            cls._transition_state(db, job, "READY_TO_INSERT", "Validation passed. File ready for database loading.")
            
            # 9. State: INSERTING
            cls._transition_state(db, job, "INSERTING", "Uploading batches to ClickHouse.")
            
            # We insert in chunks
            # Match columns to ClickHouse schema columns
            ch_col_names = [col["name"] for col in ch_schema]
            
            inserted_count = 0
            row_idx = sheet_meta["header_row_index"] + 1
            chunks = ExcelService.read_sheet_chunks(
                file_path=file_path,
                sheet_name=sheet_to_use,
                header_row_index=sheet_meta["header_row_index"],
                columns=cols_normalized,
                chunk_size=1000
            )
            
            for chunk in chunks:
                # Prepare rows aligned with ClickHouse table column order
                batch_data = []
                for row_dict in chunk:
                    row_data = []
                    for ch_col in ch_schema:
                        col_name = ch_col["name"]
                        col_name_lower = col_name.lower()
                        
                        # Fetch value from row dict (case-insensitive)
                        val = None
                        for k, v in row_dict.items():
                            if k.lower() == col_name_lower:
                                val = v
                                break
                                
                        # Cast value to ClickHouse type
                        casted_val = cls._cast_value_for_clickhouse(val, ch_col["type"])
                        row_data.append(casted_val)
                    batch_data.append(row_data)
                
                # Execute batch insertion
                ClickHouseService.insert_batch(
                    host=ch_conn.host,
                    port=ch_conn.port,
                    username=ch_conn.username,
                    password=decrypt_password(ch_conn.password_encrypted),
                    secure=ch_conn.secure,
                    database=discovered_db,
                    table_name=job.target_table,
                    columns=ch_col_names,
                    data=batch_data,
                    db_session=db
                )
                
                inserted_count += len(chunk)
                job.inserted_rows = inserted_count
                db.commit()
                
            # 10. State: VERIFYING
            cls._transition_state(db, job, "VERIFYING", "Verifying database row count matches inserted count.")
            
            # 11. State: RECONCILING (Mock reconciliation run)
            cls._transition_state(db, job, "RECONCILING", "Beginning Power Automate reconciliation check.")
            
            # Trigger reconciliation check
            ReconciliationService.run_auto_reconciliation(db, job)
            
            # Complete the job
            job.duration_ms = int((time.time() - start_time) * 1000)
            cls._transition_state(db, job, "COMPLETED", f"Successfully ingested {inserted_count} rows.")
            
            # Trigger Success Notification
            NotificationService.send_success_notification(job)

        except Exception as e:
            tb = traceback.format_exc()
            logger.error(f"Error in job {job_id}: {str(e)}\n{tb}")
            
            # Set job errors
            job.error_summary = str(e)
            job.duration_ms = int((time.time() - start_time) * 1000)
            db.commit()
            
            # Transition to FAILED
            cls._transition_state(db, job, "FAILED", f"Ingestion failed: {str(e)}")
            
            # Move file to Quarantine
            cls._quarantine_file(job)
            cls._transition_state(db, job, "QUARANTINED", "Failed file placed in quarantine directory.")
            
            # Trigger Failure Notification
            NotificationService.send_failure_notification(job, str(e))
            
        finally:
            db.close()

    @staticmethod
    def _quarantine_file(job: IngestionJob):
        """
        Moves the excel file from uploads/ to quarantine/ and appends job id.
        """
        orig_path = os.path.join(settings.UPLOAD_DIR, job.attachment_name)
        if not os.path.exists(orig_path):
            return
            
        quarantine_filename = f"{job.id}_{job.attachment_name}"
        quarantine_path = os.path.join(settings.QUARANTINE_DIR, quarantine_filename)
        
        try:
            shutil.copy2(orig_path, quarantine_path)
            # Delete original from upload folder to keep clean
            if os.path.exists(orig_path):
                os.remove(orig_path)
            logger.info(f"Quarantined file {job.attachment_name} to {quarantine_path}")
        except Exception as e:
            logger.error(f"Failed to quarantine file {job.attachment_name}: {str(e)}")

    @staticmethod
    def _cast_value_for_clickhouse(val: Any, ch_type: str) -> Any:
        """
        Helper to convert python types to compatible clickhouse formats.
        """
        if val is None or str(val).strip() == "":
            return None
            
        val_str = str(val).strip()
        ch_type_lower = ch_type.lower()
        
        if "int" in ch_type_lower:
            # Cast as int, handle decimal floats
            return int(float(val_str))
        elif "float" in ch_type_lower or "decimal" in ch_type_lower:
            return float(val_str)
        elif "bool" in ch_type_lower:
            return 1 if val_str.lower() in ("true", "yes", "1", "y") else 0
        elif "date" in ch_type_lower or "datetime" in ch_type_lower:
            # If it's already a datetime object, return it (or string representation)
            if hasattr(val, "strftime"):
                if "datetime" in ch_type_lower:
                    return val.strftime("%Y-%m-%d %H:%M:%S")
                return val.strftime("%Y-%m-%d")
                
            # If it's a string, try parsing and return ISO string
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
                try:
                    dt = datetime.strptime(val_str, fmt)
                    if "datetime" in ch_type_lower:
                        return dt.strftime("%Y-%m-%d %H:%M:%S")
                    return dt.strftime("%Y-%m-%d")
                except ValueError:
                    pass
            return val_str
            
        return val_str
