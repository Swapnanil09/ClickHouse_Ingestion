import logging
import datetime
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.app.database import engine, Base, SessionLocal
from backend.app.config import settings
from backend.app.api import auth, connections, jobs, workflow, upload, reconciliation
from backend.app.models import User, WorkflowConfig, MockClickHouseTable, ClickHouseConnection
from backend.app.api.auth import get_password_hash
from backend.app.services.outlook_poller_service import OutlookPollerService
from backend.app.services.ms_graph_service import MSGraphService

from logging.handlers import RotatingFileHandler
import os

# Ensure logs directory exists
os.makedirs("logs", exist_ok=True)

# Setup logging with rotation handler
rotating_handler = RotatingFileHandler(
    "logs/app_server.log",
    maxBytes=5 * 1024 * 1024,  # 5MB
    backupCount=5
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        rotating_handler
    ]
)
logger = logging.getLogger("app.main")

app = FastAPI(
    title="Outlook to ClickHouse Automated Ingestion Platform API",
    description="Backend processing engine, schema validator, and Power Automate integration gateway.",
    version="1.0.0"
)

from fastapi import Request
from fastapi.responses import JSONResponse
import time

# InMemory Rate Limiter
RATE_LIMIT_WINDOWS = {}  # ip -> list of timestamps
RATE_LIMIT_MAX_REQUESTS = 1000  # max requests (adjusted to accommodate active dashboard polling)
RATE_LIMIT_WINDOW_SECS = 60  # per 60 seconds

@app.middleware("http")
async def rate_limiting_middleware(request: Request, call_next):
    # Only rate-limit API endpoints
    if request.url.path.startswith("/api"):
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        
        # Get requests for this IP in the last window
        timestamps = RATE_LIMIT_WINDOWS.get(client_ip, [])
        timestamps = [t for t in timestamps if now - t < RATE_LIMIT_WINDOW_SECS]
        
        if len(timestamps) >= RATE_LIMIT_MAX_REQUESTS:
            logger.warning(f"Rate limit exceeded for IP: {client_ip}")
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please try again later."}
            )
        
        timestamps.append(now)
        RATE_LIMIT_WINDOWS[client_ip] = timestamps
        
    response = await call_next(request)
    return response

# CORS middleware config
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For prototype, open access. In production, lock down
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/api")
app.include_router(connections.router, prefix="/api")
app.include_router(jobs.router, prefix="/api")
app.include_router(workflow.router, prefix="/api")
app.include_router(upload.router, prefix="/api")
app.include_router(reconciliation.router, prefix="/api")

@app.on_event("startup")
def startup_event():
    # Production security validation
    if settings.APP_ENV == "production":
        if settings.JWT_SECRET == "supersecretjwtkeyforoutlooktochplatform2026!!!":
            logger.critical("SECURITY VIOLATION: Default JWT secret key detected in production environment!")
            raise ValueError("JWT_SECRET must be customized in production environment")
        if settings.POWER_AUTOMATE_API_KEY == "PA-Secure-Token-12345":
            logger.critical("SECURITY VIOLATION: Default Power Automate API key detected in production environment!")
            raise ValueError("POWER_AUTOMATE_API_KEY must be customized in production environment")
        logger.info("Production Security settings verified. Custom secrets active.")

    logger.info("Initializing metadata database tables...")
    Base.metadata.create_all(bind=engine)
    
    # Seeds
    db = SessionLocal()
    try:
        # 1. Seed default user if empty
        admin = db.query(User).filter(User.username == "admin").first()
        if not admin:
            admin = User(
                username="admin",
                hashed_password=get_password_hash("admin123"),
                role="admin"
            )
            db.add(admin)
            logger.info("Seeded default admin user: admin / admin123")
            
        # 2. Seed default connection if empty
        conn = db.query(ClickHouseConnection).filter(ClickHouseConnection.name == "Default Emulator Connection").first()
        if not conn:
            conn = ClickHouseConnection(
                name="Default Emulator Connection",
                host="emulated",
                port=8123,
                username="default",
                password_encrypted="encrypted",
                secure=False,
                databases_restricted="default,analytics,production"
            )
            db.add(conn)
            logger.info("Seeded default ClickHouse Connection Emulator")

        # 3. Seed default mock ClickHouse tables in emulator
        # Table 1: user_activities
        user_activities_table = db.query(MockClickHouseTable).filter(
            MockClickHouseTable.database == "default",
            MockClickHouseTable.table_name == "user_activities"
        ).first()
        if not user_activities_table:
            ch_schema1 = [
                {"name": "id", "type": "UInt32", "nullable": False, "default": None},
                {"name": "user_id", "type": "String", "nullable": False, "default": None},
                {"name": "activity", "type": "String", "nullable": False, "default": None},
                {"name": "timestamp", "type": "DateTime", "nullable": False, "default": None}
            ]
            t1 = MockClickHouseTable(
                database="default",
                table_name="user_activities",
                schema_json=ch_schema1,
                row_count=0,
                data_json=[]
            )
            db.add(t1)
            logger.info("Seeded emulator table default.user_activities")
            
        # Table 2: user_data_index
        user_data_table = db.query(MockClickHouseTable).filter(
            MockClickHouseTable.database == "analytics",
            MockClickHouseTable.table_name == "user_data_index"
        ).first()
        if not user_data_table:
            ch_schema2 = [
                {"name": "id", "type": "UInt32", "nullable": False, "default": None},
                {"name": "email", "type": "String", "nullable": False, "default": None},
                {"name": "status", "type": "String", "nullable": True, "default": None},
                {"name": "created_at", "type": "Date", "nullable": False, "default": None}
            ]
            t2 = MockClickHouseTable(
                database="analytics",
                table_name="user_data_index",
                schema_json=ch_schema2,
                row_count=0,
                data_json=[]
            )
            db.add(t2)
            logger.info("Seeded emulator table analytics.user_data_index")

        # 4. Seed default workflow rules if empty
        wf = db.query(WorkflowConfig).filter(WorkflowConfig.name == "Default Ingestion Config").first()
        if not wf:
            default_config = WorkflowConfig(
                name="Default Ingestion Config",
                email_subject_pattern=".*upload_request.*",
                attachment_pattern=".*\\.xlsx",
                allowed_senders="*",
                target_extraction_rules={"table_regex": "table:\\s*([a-zA-Z0-9_]+)"},
                mode="STRICT"
            )
            db.add(default_config)
            logger.info("Seeded default workflow configuration")

        db.commit()
    except Exception as e:
        logger.error(f"Error seeding database: {str(e)}")
        db.rollback()
    finally:
        db.close()
        
    logger.info("FastAPI Application fully loaded.")
    OutlookPollerService.start_poller()
    MSGraphService.start_service()

@app.on_event("shutdown")
def shutdown_event():
    logger.info("Stopping Outlook Direct Poller...")
    OutlookPollerService.stop_poller()
    logger.info("Stopping MS Graph Mail Listener...")
    MSGraphService.stop_service()

@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "database": "sqlite/metadata.db",
        "allowed_databases": settings.ALLOWED_DATABASES.split(",")
    }
