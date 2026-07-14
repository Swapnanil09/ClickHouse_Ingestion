from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from backend.app.database import get_db
from backend.app.models import ClickHouseConnection, MockClickHouseTable, AuditLog
from backend.app.schemas import (
    ClickHouseConnectionCreate, ClickHouseConnectionResponse, 
    MockClickHouseTableCreate, MockClickHouseTableResponse
)
from backend.app.services.clickhouse_service import ClickHouseService
from backend.app.api.auth import get_current_user
import datetime
from backend.app.utils.security import encrypt_password, decrypt_password

router = APIRouter(prefix="/connections", tags=["clickhouse-connections"])

@router.post("", response_model=ClickHouseConnectionResponse)
def create_connection(
    conn_in: ClickHouseConnectionCreate, 
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user)
):
    # Mask password or decrypt/encrypt inside connection
    # For prototype, we will store simple password (in production, we'd use cryptography module)
    # Check if name already exists
    existing = db.query(ClickHouseConnection).filter(ClickHouseConnection.name == conn_in.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Connection with this name already exists")
        
    # Deactivate others if this is active
    db.query(ClickHouseConnection).update({ClickHouseConnection.is_active: False})
    
    conn = ClickHouseConnection(
        name=conn_in.name,
        host=conn_in.host,
        port=conn_in.port,
        username=conn_in.username,
        password_encrypted=encrypt_password(conn_in.password),
        secure=conn_in.secure,
        databases_restricted=conn_in.databases_restricted,
        is_active=True
    )
    db.add(conn)
    
    # Audit log
    audit = AuditLog(
        actor=current_user.username,
        action="CREATE_CONNECTION",
        details=f"Created connection '{conn.name}' pointing to {conn.host}:{conn.port}"
    )
    db.add(audit)
    
    db.commit()
    db.refresh(conn)
    return conn

@router.get("", response_model=List[ClickHouseConnectionResponse])
def get_connections(db: Session = Depends(get_db), current_user: Any = Depends(get_current_user)):
    return db.query(ClickHouseConnection).all()

@router.post("/{conn_id}/test")
def test_connection_by_id(
    conn_id: int, 
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user)
):
    conn = db.query(ClickHouseConnection).filter(ClickHouseConnection.id == conn_id).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
        
    ok, msg = ClickHouseService.test_connection(
        host=conn.host,
        port=conn.port,
        username=conn.username,
        password=decrypt_password(conn.password_encrypted),
        secure=conn.secure,
        db_session=db
    )
    
    conn.last_tested = datetime.datetime.utcnow()
    db.commit()
    
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"message": msg}

@router.post("/test-raw")
def test_raw_connection(
    conn_in: ClickHouseConnectionCreate, 
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user)
):
    ok, msg = ClickHouseService.test_connection(
        host=conn_in.host,
        port=conn_in.port,
        username=conn_in.username,
        password=conn_in.password,
        secure=conn_in.secure,
        db_session=db
    )
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"message": msg}

@router.get("/active/databases", response_model=List[str])
def get_active_databases(db: Session = Depends(get_db), current_user: Any = Depends(get_current_user)):
    conn = db.query(ClickHouseConnection).filter(ClickHouseConnection.is_active == True).first()
    if not conn:
        raise HTTPException(status_code=400, detail="No active ClickHouse connection is configured")
        
    return ClickHouseService.discover_databases(
        conn.host, conn.port, conn.username, decrypt_password(conn.password_encrypted), conn.secure, db
    )

@router.get("/active/databases/{database}/tables", response_model=List[str])
def get_active_tables(
    database: str, 
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user)
):
    conn = db.query(ClickHouseConnection).filter(ClickHouseConnection.is_active == True).first()
    if not conn:
        raise HTTPException(status_code=400, detail="No active ClickHouse connection is configured")
        
    return ClickHouseService.discover_tables(
        conn.host, conn.port, conn.username, decrypt_password(conn.password_encrypted), conn.secure, database, db
    )

@router.get("/active/databases/{database}/tables/{table_name}/schema")
def get_table_schema(
    database: str, 
    table_name: str, 
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user)
):
    conn = db.query(ClickHouseConnection).filter(ClickHouseConnection.is_active == True).first()
    if not conn:
        raise HTTPException(status_code=400, detail="No active ClickHouse connection is configured")
        
    schema = ClickHouseService.get_table_schema(
        conn.host, conn.port, conn.username, decrypt_password(conn.password_encrypted), conn.secure, database, table_name, db
    )
    if not schema:
        raise HTTPException(status_code=404, detail=f"Table {database}.{table_name} not found")
    return schema

# Emulator helper routes to configure simulated tables and schemas
@router.post("/emulator/tables", response_model=MockClickHouseTableResponse)
def create_emulator_table(
    table_in: MockClickHouseTableCreate,
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user)
):
    schema_list = [field.dict() for field in table_in.schema_fields]
    mock_table = ClickHouseService.create_mock_table_in_emulator(
        database=table_in.database,
        table_name=table_in.table_name,
        schema=schema_list,
        db_session=db
    )
    return mock_table

@router.get("/emulator/tables", response_model=List[MockClickHouseTableResponse])
def get_emulator_tables(db: Session = Depends(get_db), current_user: Any = Depends(get_current_user)):
    return db.query(MockClickHouseTable).all()

@router.delete("/emulator/tables/{table_id}")
def delete_emulator_table(table_id: int, db: Session = Depends(get_db), current_user: Any = Depends(get_current_user)):
    table = db.query(MockClickHouseTable).filter(MockClickHouseTable.id == table_id).first()
    if not table:
        raise HTTPException(status_code=404, detail="Table not found")
    db.delete(table)
    db.commit()
    return {"message": "Mock table deleted."}

@router.get("/emulator/tables/{table_id}/data")
def get_emulator_table_data(table_id: int, db: Session = Depends(get_db), current_user: Any = Depends(get_current_user)):
    table = db.query(MockClickHouseTable).filter(MockClickHouseTable.id == table_id).first()
    if not table:
        raise HTTPException(status_code=404, detail="Table not found")
    return table.data_json
