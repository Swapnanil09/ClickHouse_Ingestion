import os
from pydantic_settings import BaseSettings
from typing import List

class Settings(BaseSettings):
    # Environment Control
    APP_ENV: str = "development"  # "development" or "production"
    SANDBOX_MODE: bool = True     # If True, fallbacks to mock APIs when keys are missing/invalid
    
    # Security
    JWT_SECRET: str = "supersecretjwtkeyforoutlooktochplatform2026!!!"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 1 day
    
    # API Verification for Power Automate and Webhooks
    POWER_AUTOMATE_API_KEY: str = "PA-Secure-Token-12345"
    
    # Metadata DB (PostgreSQL in production, SQLite for local dev/prototype)
    DATABASE_URL: str = "sqlite:///./metadata.db"
    
    # ClickHouse Connection (for emulated mode / real connection fallback)
    CLICKHOUSE_HOST: str = "emulated"
    CLICKHOUSE_PORT: int = 8123
    CLICKHOUSE_USERNAME: str = "default"
    CLICKHOUSE_PASSWORD: str = ""
    CLICKHOUSE_DATABASE: str = "default"
    CLICKHOUSE_SECURE: bool = False
    
    # Path settings
    UPLOAD_DIR: str = "./uploads"
    QUARANTINE_DIR: str = "./quarantine"
    
    # Allowed ClickHouse databases for AUTO-discovery
    ALLOWED_DATABASES: str = "default,analytics,production,staging"
    
    # Direct Outlook Mailbox Poller Settings (Optional)
    OUTLOOK_IMAP_SERVER: str = "outlook.office365.com"
    OUTLOOK_IMAP_PORT: int = 993
    OUTLOOK_EMAIL: str = ""
    OUTLOOK_PASSWORD: str = ""
    OUTLOOK_POLL_INTERVAL_SECS: int = 0  # 0 means disabled by default
    
    # Microsoft Entra ID (Azure AD) OAuth / Graph settings (For Auto-connection)
    MICROSOFT_CLIENT_ID: str = "mock-client-id-12345"
    MICROSOFT_CLIENT_SECRET: str = "mock-client-secret-12345"
    MICROSOFT_TENANT_ID: str = "common"
    MICROSOFT_REDIRECT_URI: str = "http://localhost:8081/api/auth/microsoft/callback"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()

# Ensure directories exist
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
os.makedirs(settings.QUARANTINE_DIR, exist_ok=True)
