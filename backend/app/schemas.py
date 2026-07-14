from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Union
from datetime import datetime

# Token & Auth schemas
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

class UserLogin(BaseModel):
    username: str
    password: str

class UserCreate(BaseModel):
    username: str
    password: str
    role: str = "operator"

class UserResponse(BaseModel):
    id: int
    username: str
    role: str
    
    class Config:
        from_attributes = True

# ClickHouseConnection schemas
class ClickHouseConnectionCreate(BaseModel):
    name: str
    host: str
    port: int = 8123
    username: str
    password: str
    secure: bool = False
    databases_restricted: str = "default"

class ClickHouseConnectionResponse(BaseModel):
    id: int
    name: str
    host: str
    port: int
    username: str
    secure: bool
    databases_restricted: str
    is_active: bool
    last_tested: Optional[datetime] = None

    class Config:
        from_attributes = True

# WorkflowConfig schemas
class WorkflowConfigCreate(BaseModel):
    name: str
    email_subject_pattern: Optional[str] = None
    attachment_pattern: Optional[str] = None
    allowed_senders: Optional[str] = "*"
    target_extraction_rules: Optional[Dict[str, Any]] = None
    mode: str = "STRICT"

class WorkflowConfigResponse(BaseModel):
    id: int
    name: str
    email_subject_pattern: Optional[str] = None
    attachment_pattern: Optional[str] = None
    allowed_senders: Optional[str] = None
    target_extraction_rules: Optional[Dict[str, Any]] = None
    mode: str

    class Config:
        from_attributes = True

# ValidationError schema
class ValidationErrorResponse(BaseModel):
    id: int
    row_number: Optional[int] = None
    column_name: Optional[str] = None
    expected_type: Optional[str] = None
    actual_value: Optional[str] = None
    error_reason: str

    class Config:
        from_attributes = True

# State History schema
class JobStateHistoryResponse(BaseModel):
    id: int
    previous_state: Optional[str] = None
    new_state: str
    timestamp: datetime
    reason: Optional[str] = None
    actor: str

    class Config:
        from_attributes = True

# Reconciliation Run schema
class ReconciliationRunResponse(BaseModel):
    id: int
    email_id: Optional[str] = None
    attachment_hash: Optional[str] = None
    target_database: Optional[str] = None
    target_table: Optional[str] = None
    backend_row_count: int
    pa_row_count: int
    match_status: str
    discrepancy_details: Optional[str] = None
    run_timestamp: datetime

    class Config:
        from_attributes = True

# IngestionJob schemas
class IngestionJobResponse(BaseModel):
    id: str
    correlation_id: str
    email_id: Optional[str] = None
    sender: Optional[str] = None
    subject: Optional[str] = None
    received_time: Optional[datetime] = None
    attachment_name: Optional[str] = None
    attachment_size: Optional[int] = None
    attachment_hash: Optional[str] = None
    target_database: Optional[str] = None
    target_table: Optional[str] = None
    sheet_name: Optional[str] = None
    status: str
    processing_mode: str
    total_rows: int
    valid_rows: int
    invalid_rows: int
    inserted_rows: int
    duration_ms: int
    error_summary: Optional[str] = None
    retry_count: int
    reconciliation_status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class IngestionJobDetailResponse(IngestionJobResponse):
    state_history: List[JobStateHistoryResponse] = []
    validation_errors: List[ValidationErrorResponse] = []
    reconciliation_runs: List[ReconciliationRunResponse] = []

    class Config:
        from_attributes = True

# AuditLog schemas
class AuditLogResponse(BaseModel):
    id: int
    timestamp: datetime
    actor: str
    action: str
    job_id: Optional[str] = None
    details: Optional[str] = None

    class Config:
        from_attributes = True

# Emulator Mock ClickHouse Table schema
class MockClickHouseColumnSchema(BaseModel):
    name: str
    type: str
    nullable: bool = False
    default: Optional[str] = None

class MockClickHouseTableCreate(BaseModel):
    database: str = "default"
    table_name: str
    schema_fields: List[MockClickHouseColumnSchema]

class MockClickHouseTableResponse(BaseModel):
    id: int
    database: str
    table_name: str
    schema_json: List[Dict[str, Any]]
    row_count: int

    class Config:
        from_attributes = True

# Power Automate Webhook request payload
class PowerAutomateIngestRequest(BaseModel):
    email_id: str
    sender: str
    subject: str
    received_time: str
    attachment_name: str
    file_content_base64: str  # Send file encoded in base64
    workflow_run_id: Optional[str] = None
    
    # Target configurations
    target_table: str
    target_database: Optional[str] = "AUTO"
    processing_mode: Optional[str] = "STRICT"
    sheet_name: Optional[str] = None  # Optional, if None, process first sheet

class PowerAutomateReconcileRequest(BaseModel):
    ingestion_job_id: str
    email_id: str
    attachment_hash: str
    target_database: str
    target_table: str
    expected_row_count: int
    status: str
