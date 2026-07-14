# System Installation & Production Setup Guide

This document provides step-by-step instructions for deploying the automated Excel-to-ClickHouse ingestion platform in local development, docker staging, and scaled production environments.

---

## 1. System Prerequisites

### Supported Operating Systems
*   **Local Development**: Windows 10/11, macOS, Linux (Ubuntu 22.04 LTS recommended)
*   **Staging / Production**: Linux (Ubuntu 20.04/22.04 LTS or Amazon Linux 2)

### Required Software Packages
*   **Python**: Version 3.10 to 3.14 (3.14.3 used locally)
*   **NodeJS**: Version 18.x to 24.x (v24.15.0 used locally)
*   **Docker**: Version 20.x or above (with Compose v2)
*   **PostgreSQL**: Version 14 or above (metadata/audit database)
*   **ClickHouse**: Version 23.x or above (target Data Warehouse)

---

## 2. Environment Variables (.env)

Create a `.env` file in the `backend/` root directory using the following keys:

```ini
# --- SECURITY ---
# Secret key used for signing JWT login tokens
JWT_SECRET=super_secret_jwt_signing_token_for_production_2026_xyz
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440

# Secret token required from Power Automate webhook requests
POWER_AUTOMATE_API_KEY=PA-Secure-Token-12345

# --- METADATA PERSISTENCE (POSTGRESQL) ---
# Format: postgresql://username:password@host:port/database
# For local prototype development, sqlite is supported by default:
DATABASE_URL=sqlite:///./metadata.db

# --- CLICKHOUSE DATA TARGETS ---
# Set host to "emulated" to use local sqlite tables instead of real ClickHouse server
CLICKHOUSE_HOST=emulated
CLICKHOUSE_PORT=8123
CLICKHOUSE_USERNAME=default
CLICKHOUSE_PASSWORD=
CLICKHOUSE_DATABASE=default
CLICKHOUSE_SECURE=False

# --- PIPELINE DIRECTORIES ---
UPLOAD_DIR=./uploads
QUARANTINE_DIR=./quarantine

# --- ALLOWED DATABASES FOR AUTO-DISCOVERY ---
ALLOWED_DATABASES=default,analytics,production,staging

# --- DIRECT OUTLOOK MAILBOX POLLING (OPTIONAL ALTERNATIVE TO POWER AUTOMATE) ---
# Enable this to let the backend scan an Outlook inbox directly via IMAP
OUTLOOK_IMAP_SERVER=outlook.office365.com
OUTLOOK_IMAP_PORT=993
OUTLOOK_EMAIL=
OUTLOOK_PASSWORD=
OUTLOOK_POLL_INTERVAL_SECS=0  # Set > 0 (e.g. 30) to enable direct polling
```

---

## 3. Step-by-Step Installation

### 3.1 Backend Deployment
1.  Navigate to the `backend/` directory:
    ```bash
    cd backend
    ```
2.  Create a python virtual environment and activate it:
    ```bash
    python -m venv venv
    # Windows:
    .\venv\Scripts\activate
    # macOS/Linux:
    source venv/bin/activate
    ```
3.  Install python dependencies:
    ```bash
    pip install -r requirements.txt
    ```
4.  Run the backend:
    ```bash
    python run.py
    ```

### 3.2 Frontend Deployment
1.  Navigate to the `frontend/` directory:
    ```bash
    cd ../frontend
    ```
2.  Install npm packages:
    ```bash
    npm install
    ```
3.  Launch the Vite hot-reloading development server:
    ```bash
    npm run dev
    ```

---

## 4. Microsoft Power Automate Setup Steps

To set up the ingestion automation flow in Microsoft Power Automate, create a **Cloud Flow** containing the following sequence of blocks:

```mermaid
graph TD
    Trigger["Outlook: When a new email arrives V3"]
    FilterSubject["Condition: Subject contains 'upload_request'"]
    GetAttach["Outlook: Get Attachment V2"]
    ConvertB64["Compose: base64(Attachment ContentBytes)"]
    SendHTTP["HTTP Action: POST to backend/api/upload/webhook"]
    ReconHTTP["HTTP Action: POST to backend/api/reconciliation"]
    SendEmail["Outlook: Send email confirmation Success/Failure"]
    
    Trigger --> FilterSubject
    FilterSubject -->|Yes| GetAttach
    GetAttach --> ConvertB64
    ConvertB64 --> SendHTTP
    SendHTTP --> ReconHTTP
    ReconHTTP --> SendEmail
```

### Steps to Reproduce the Flow:
1.  **Trigger**: Select *Office 365 Outlook - When a new email arrives (V3)*.
    *   **Folder**: Inbox.
    *   **Only with Attachments**: Yes.
    *   **Include Attachments**: Yes.
2.  **Filter Condition**: Add a condition checking that the **Subject** contains `upload_request`.
3.  **Process Attachments Loop**: Add an *Apply to each* loop referencing `Attachments` list.
4.  **Base64 Encoder**: Add a *Data Operation - Compose* block. Expression:
    `base64(items('Apply_to_each')?['contentBytes'])`
5.  **Webhook HTTP POST**: Add an *HTTP* action (rename the action block to `HTTP_Webhook` for expression compatibility) configured as follows:
    *   **Method**: `POST`
    *   **URI**: `https://your-domain.com/api/upload/webhook`
    *   **Headers**:
        *   `X-API-KEY`: `PA-Secure-Token-12345`
        *   `Content-Type`: `application/json`
    *   **Body** (JSON):
        ```json
        {
          "email_id": "@{triggerOutputs()?['body/id']}",
          "sender": "@{triggerOutputs()?['body/from']}",
          "subject": "@{triggerOutputs()?['body/subject']}",
          "received_time": "@{triggerOutputs()?['body/receivedDateTime']}",
          "attachment_name": "@{items('Apply_to_each')?['name']}",
          "file_content_base64": "@{outputs('Compose')}",
          "target_table": "user_activities",
          "target_database": "AUTO",
          "processing_mode": "STRICT"
        }
        ```
6.  **Reconciliation POST**: Add another *HTTP* block at the end of the loop:
    *   **Method**: `POST`
    *   **URI**: `https://your-domain.com/api/reconciliation`
    *   **Headers**:
        *   `X-API-KEY`: `PA-Secure-Token-12345`
        *   `Content-Type`: `application/json`
    *   **Body**:
        ```json
        {
          "ingestion_job_id": "@{body('HTTP_Webhook')?['id']}",
          "email_id": "@{triggerOutputs()?['body/id']}",
          "attachment_hash": "@{body('HTTP_Webhook')?['attachment_hash']}",
          "target_database": "@{body('HTTP_Webhook')?['target_database']}",
          "target_table": "@{body('HTTP_Webhook')?['target_table']}",
          "expected_row_count": @{body('HTTP_Webhook')?['total_rows']},
          "status": "@{body('HTTP_Webhook')?['status']}"
        }
        ```

---

## 5. ClickHouse Least-Privilege Role Setup

For production database integration, create a dedicated data loader user. Do not connect using the default admin account. Execute the following commands in ClickHouse (`clickhouse-client`):

```sql
-- 1. Create role
CREATE ROLE excel_loader_role;

-- 2. Grant permissions on targeted database (e.g. analytics)
GRANT SHOW ON analytics.* TO excel_loader_role;
GRANT SELECT, INSERT, CREATE TABLE ON analytics.* TO excel_loader_role;

-- 3. Create dedicated application user
CREATE USER excel_ingestion_user IDENTIFIED WITH sha256_password BY 'SecureLoaderPass2026!';

-- 4. Assign role
GRANT excel_loader_role TO excel_ingestion_user;
```

---

## 6. Docker Compose Deployment

For production deployments, the stack can be run using Docker Compose, creating isolated frontend, backend, PostgreSQL, and ClickHouse containers.

Create `docker-compose.yml` in the root:

```yaml
version: '3.8'

services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_USER: pguser
      POSTGRES_PASSWORD: pgpassword
      POSTGRES_DB: ingestion_metadata
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

  clickhouse:
    image: clickhouse/clickhouse-server:latest
    ports:
      - "8123:8123"
      - "9000:9000"
    volumes:
      - chdata:/var/lib/clickhouse

  backend:
    build: ./backend
    ports:
      - "8081:8081"
    environment:
      - DATABASE_URL=postgresql://pguser:pgpassword@postgres:5432/ingestion_metadata
      - CLICKHOUSE_HOST=clickhouse
      - CLICKHOUSE_PORT=8123
    depends_on:
      - postgres
      - clickhouse

  frontend:
    build: ./frontend
    ports:
      - "80:80"
    depends_on:
      - backend

volumes:
  pgdata:
  chdata:
```

---

## 7. Production Security & reverse Proxy

In production, run the application backend behind a reverse proxy (like **Nginx**) to manage HTTPS SSL encryption and TLS certificate renewal (using **Let's Encrypt**).

### Nginx Server Block (Nginx.conf) Example:
```nginx
server {
    listen 80;
    server_name ingestion.company.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name ingestion.company.com;

    ssl_certificate /etc/letsencrypt/live/ingestion.company.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/ingestion.company.com/privkey.pem;

    # Backend redirection
    location /api {
        proxy_pass http://127.0.0.1:8081;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Frontend redirection
    location / {
        proxy_pass http://127.0.0.1:5173;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

---

## 8. Backup & Disaster Recovery

### Metadata Backup
Execute nightly crontab dump backups for PostgreSQL:
```bash
pg_dump -U pguser -h localhost -d ingestion_metadata > /var/backups/pg_metadata_$(date +%F).sql
```

### Quarantine File Backups
Sync quarantine folders to secure cloud buckets (e.g. AWS S3 or Azure Blob) using a cron script:
```bash
aws s3 sync /opt/ingestion/quarantine s3://company-quarantine-backups/files/
```

---

## 9. Direct Outlook Mailbox Integration Channels

To avoid manually building Microsoft Power Automate flows, the Ingestion Gateway supports two optional native polling methods:

### 9.1 Channel A: Direct IMAP Poller
*   **Mechanism**: Connects directly to the Outlook IMAP server (`outlook.office365.com` on port 993) using an email and password/app-password.
*   **Setup**: Configure `.env` parameters:
    *   `OUTLOOK_POLL_INTERVAL_SECS`: Set > 0 (e.g. `30`).
    *   `OUTLOOK_EMAIL`: Your Outlook email.
    *   `OUTLOOK_PASSWORD`: Your Outlook password or App Password.

### 9.2 Channel B: Direct Microsoft Graph API Poller (Auto-Authentication)
*   **Mechanism**: The operator signs in directly via their Microsoft Account on the dashboard. The backend obtains an OAuth 2.0 access/refresh token and automatically polls the user's Office 365 Inbox using official MS Graph API calls.
*   **Configuration**: Register an Application in the **Azure Active Directory Portal (App Registrations)**:
    1.  Add Redirect URI: `http://localhost:8081/api/auth/microsoft/callback`.
    2.  Grant API Permissions: `Mail.ReadWrite`, `offline_access`, `User.Read`.
    3.  Choose one of the connection methods:
        *   **Method A: Web UI Configuration (Recommended)**: Expand **Manual Config** directly under the *Connect Microsoft Account* card on the dashboard, input your Azure Client ID, Client Secret, and Tenant ID, and click *Save Config & Authenticate*. The backend writes these parameters securely to the local SQLite database.
        *   **Method B: Environment Configuration**: Configure `.env` variables directly:
            ```ini
            MICROSOFT_CLIENT_ID=your-azure-app-client-id
            MICROSOFT_CLIENT_SECRET=your-azure-app-client-secret
            MICROSOFT_TENANT_ID=common
            MICROSOFT_REDIRECT_URI=http://localhost:8081/api/auth/microsoft/callback
            ```
*   **Operation**: Click **Connect Microsoft Account** on the dashboard. This exchanges authorization codes for long-lived OAuth refresh tokens, and activates the automatic background listener process.

---

## 10. Production Hardening & Operational Safety

The platform incorporates several industry-grade engineering practices designed to move beyond prototype stages and ensure secure, reliable production operations:

### 10.1 ClickHouse Connection Password Encryption
*   **Implementation**: All password properties submitted when creating or updating ClickHouse connections are automatically encrypted symmetrically before writing to the database metadata store.
*   **Security standard**: Uses AES encryption via the Python `cryptography.fernet` library.
*   **Key derivation**: The encryption key is derived deterministically from the server's `JWT_SECRET` (configured via `.env`). If the database credentials are leaked or exposed, the connection passwords remain fully secure. Decryption happens purely in memory during ingestion runs.

### 10.2 API Rate Limiting Middleware
*   **Implementation**: An ASGI HTTP rate limiting middleware operates on all incoming API requests (e.g. webhook triggers, auth logins).
*   **Limitation**: Restricts requests to `100 requests per minute` per unique client IP address. 
*   **Response**: Exceeding this limit yields a standard HTTP `429 Too Many Requests` status code, defending the validation pipeline and database against brute-force logins or DDOS attempts.

### 10.3 Rotating Rotational Logging System
*   **Implementation**: Utilizes `RotatingFileHandler` to record server logs.
*   **Storage**: Logs are automatically written to `logs/app_server.log`.
*   **Rotation policies**: Prevents infinite log expansion. Files are split at `5MB` limits, retaining up to `5` historical backup files (`app_server.log.1`, `app_server.log.2`, etc.) before recycling, preventing server disk crashes.

### 10.4 Startup Key Safety Validator
*   **Implementation**: When setting `APP_ENV=production` inside `.env`, the FastAPI application runs a series of strict security checks at start-up.
*   **Rules**: If the default prototype secret keys are detected (such as `supersecretjwtkey...` or `PA-Secure-Token-12345`), the server immediately outputs a `CRITICAL` log and raises a start-up validation error, shutting down the process. This ensures weak default keys are never accidentally deployed in staging or production.


