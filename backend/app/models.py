import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Float, JSON
from sqlalchemy.orm import relationship
from backend.app.database import Base

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(String, default="operator")  # admin, operator, viewer

class ClickHouseConnection(Base):
    __tablename__ = "clickhouse_connections"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    host = Column(String, nullable=False)
    port = Column(Integer, default=8123)
    username = Column(String, nullable=False)
    password_encrypted = Column(String, nullable=False)  # We will mask this in APIs
    secure = Column(Boolean, default=False)
    databases_restricted = Column(String, default="default")  # Comma separated
    is_active = Column(Boolean, default=True)
    last_tested = Column(DateTime, nullable=True)

class WorkflowConfig(Base):
    __tablename__ = "workflow_configs"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    email_subject_pattern = Column(String, nullable=True)  # Regex or contains pattern
    attachment_pattern = Column(String, nullable=True)     # Regex or glob pattern
    allowed_senders = Column(Text, nullable=True)          # Comma separated or *
    target_extraction_rules = Column(JSON, nullable=True)  # Extraction regex/rules
    mode = Column(String, default="STRICT")                # STRICT or RELAXED

class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"
    
    id = Column(String, primary_key=True, index=True)  # We will use UUID or correlation ID
    correlation_id = Column(String, index=True)
    email_id = Column(String, index=True, nullable=True)
    sender = Column(String, nullable=True)
    subject = Column(String, nullable=True)
    received_time = Column(DateTime, nullable=True)
    attachment_name = Column(String, nullable=True)
    attachment_size = Column(Integer, nullable=True)
    attachment_hash = Column(String, nullable=True)
    target_database = Column(String, nullable=True)
    target_table = Column(String, nullable=True)
    sheet_name = Column(String, nullable=True)
    status = Column(String, default="EMAIL_RECEIVED")  # EMAIL_RECEIVED, ATTACHMENT_RECEIVED, etc.
    processing_mode = Column(String, default="STRICT")
    total_rows = Column(Integer, default=0)
    valid_rows = Column(Integer, default=0)
    invalid_rows = Column(Integer, default=0)
    inserted_rows = Column(Integer, default=0)
    duration_ms = Column(Integer, default=0)
    error_summary = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0)
    reconciliation_status = Column(String, default="PENDING")  # PENDING, MATCHED, MISMATCHED
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    
    state_history = relationship("JobStateHistory", back_populates="job", cascade="all, delete-orphan")
    validation_errors = relationship("ValidationError", back_populates="job", cascade="all, delete-orphan")
    reconciliation_runs = relationship("ReconciliationRun", back_populates="job", cascade="all, delete-orphan")

class JobStateHistory(Base):
    __tablename__ = "job_state_history"
    
    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(String, ForeignKey("ingestion_jobs.id"), nullable=False)
    previous_state = Column(String, nullable=True)
    new_state = Column(String, nullable=False)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    reason = Column(String, nullable=True)
    actor = Column(String, default="system")
    
    job = relationship("IngestionJob", back_populates="state_history")

class ValidationError(Base):
    __tablename__ = "validation_errors"
    
    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(String, ForeignKey("ingestion_jobs.id"), nullable=False)
    row_number = Column(Integer, nullable=True)  # Null if file/schema error
    column_name = Column(String, nullable=True)
    expected_type = Column(String, nullable=True)
    actual_value = Column(String, nullable=True)
    error_reason = Column(String, nullable=False)
    
    job = relationship("IngestionJob", back_populates="validation_errors")

class ReconciliationRun(Base):
    __tablename__ = "reconciliation_runs"
    
    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(String, ForeignKey("ingestion_jobs.id"), nullable=False)
    email_id = Column(String, nullable=True)
    attachment_hash = Column(String, nullable=True)
    target_database = Column(String, nullable=True)
    target_table = Column(String, nullable=True)
    backend_row_count = Column(Integer, default=0)
    pa_row_count = Column(Integer, default=0)
    match_status = Column(String, nullable=False)  # MATCHED, MISMATCHED
    discrepancy_details = Column(Text, nullable=True)
    run_timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    
    job = relationship("IngestionJob", back_populates="reconciliation_runs")

class AuditLog(Base):
    __tablename__ = "audit_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    actor = Column(String, nullable=False)
    action = Column(String, nullable=False)
    job_id = Column(String, nullable=True)
    details = Column(Text, nullable=True)

# Emulator DB models (To store mock schemas and mock tables for prototype)
class MockClickHouseTable(Base):
    __tablename__ = "mock_clickhouse_tables"
    
    id = Column(Integer, primary_key=True, index=True)
    database = Column(String, nullable=False, default="default")
    table_name = Column(String, nullable=False)
    schema_json = Column(JSON, nullable=False)  # List of dicts: {"name": col_name, "type": type_str, "nullable": bool, "default": optional_val}
    row_count = Column(Integer, default=0)
    
    # We will simulate writing data by saving rows in a json column for validation and querying
    data_json = Column(JSON, default=list)
