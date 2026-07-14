from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from backend.app.database import get_db
from backend.app.models import WorkflowConfig, AuditLog
from backend.app.schemas import WorkflowConfigCreate, WorkflowConfigResponse
from backend.app.api.auth import get_current_user

router = APIRouter(prefix="/workflows", tags=["workflow-configurations"])

@router.post("", response_model=WorkflowConfigResponse)
def create_workflow_config(
    config_in: WorkflowConfigCreate,
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user)
):
    existing = db.query(WorkflowConfig).filter(WorkflowConfig.name == config_in.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Workflow configuration with this name already exists")
        
    config = WorkflowConfig(
        name=config_in.name,
        email_subject_pattern=config_in.email_subject_pattern,
        attachment_pattern=config_in.attachment_pattern,
        allowed_senders=config_in.allowed_senders,
        target_extraction_rules=config_in.target_extraction_rules,
        mode=config_in.mode
    )
    db.add(config)
    
    # Audit log
    audit = AuditLog(
        actor=current_user.username,
        action="CREATE_WORKFLOW_CONFIG",
        details=f"Created workflow rules '{config.name}'"
    )
    db.add(audit)
    
    db.commit()
    db.refresh(config)
    return config

@router.get("", response_model=List[WorkflowConfigResponse])
def get_workflows(db: Session = Depends(get_db), current_user: Any = Depends(get_current_user)):
    # Create default rule if none exist to make it run out of the box
    configs = db.query(WorkflowConfig).all()
    if not configs:
        default_config = WorkflowConfig(
            name="Default Ingestion Config",
            email_subject_pattern=".*upload_request.*",
            attachment_pattern=".*\\.xlsx",
            allowed_senders="*",
            target_extraction_rules={"table_regex": "table:\\s*([a-zA-Z0-9_]+)"},
            mode="STRICT"
        )
        db.add(default_config)
        db.commit()
        configs = [default_config]
    return configs

@router.put("/{config_id}", response_model=WorkflowConfigResponse)
def update_workflow_config(
    config_id: int,
    config_in: WorkflowConfigCreate,
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user)
):
    config = db.query(WorkflowConfig).filter(WorkflowConfig.id == config_id).first()
    if not config:
        raise HTTPException(status_code=404, detail="Workflow config not found")
        
    config.name = config_in.name
    config.email_subject_pattern = config_in.email_subject_pattern
    config.attachment_pattern = config_in.attachment_pattern
    config.allowed_senders = config_in.allowed_senders
    config.target_extraction_rules = config_in.target_extraction_rules
    config.mode = config_in.mode
    
    # Audit log
    audit = AuditLog(
        actor=current_user.username,
        action="UPDATE_WORKFLOW_CONFIG",
        details=f"Updated workflow rules '{config.name}'"
    )
    db.add(audit)
    
    db.commit()
    db.refresh(config)
    return config

@router.delete("/{config_id}")
def delete_workflow_config(
    config_id: int,
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user)
):
    config = db.query(WorkflowConfig).filter(WorkflowConfig.id == config_id).first()
    if not config:
        raise HTTPException(status_code=404, detail="Workflow config not found")
        
    db.delete(config)
    
    # Audit log
    audit = AuditLog(
        actor=current_user.username,
        action="DELETE_WORKFLOW_CONFIG",
        details=f"Deleted workflow rules '{config.name}'"
    )
    db.add(audit)
    
    db.commit()
    return {"message": "Workflow configuration deleted."}
