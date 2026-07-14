# End-to-End Integration & Connection Workflow Guide

This document describes how to connect Microsoft Outlook, Microsoft Power Automate, the Ngrok gateway tunnel, the FastAPI backend service, and the ClickHouse database emulator to establish the end-to-end data ingestion pipeline.

---

## 1. System Integration Flow Diagram

The diagram below outlines the communication path of the data payload and reconciliation tokens across both cloud and local environments:

```text
+-----------------------------------+
|       Microsoft Cloud (O365)      |
|  [Email with Excel Attachment]    |
+-----------------+-----------------+
                  |
                  ▼
+-----------------+-----------------+
|     Microsoft Power Automate      |
|  - Triggers on Subject            |
|  - Encodes Attachment (Base64)     |
+-----------------+-----------------+
                  |
                  ▼ (POST Payload to Public HTTPS URI)
+-----------------+-----------------+
|        Ngrok Tunnel Gateway       |
|  (Proxies Public -> localhost)    |
+-----------------+-----------------+
                  |
                  ▼ (localhost:8000 redirect)
+-----------------+-----------------+
|     FastAPI Backend Application   |
|  - Creates Ingestion Job          |
|  - Runs Validation (Layers 1-5)   |
|  - Inserts Batches to ClickHouse  |
+-----------------+-----------------+
                  |
                  ▼ (Loads verified rows)
+-----------------+-----------------+
|     ClickHouse Target Database    |
|       (Emulator or Server)        |
+-----------------+-----------------+
                  |
                  ▼ (Reconciliation row count check)
+-----------------+-----------------+
|     Power Automate Flow Ends      |
|  - Calls /api/reconciliation      |
|  - Triggers Success/Failure Email |
+-----------------------------------+
```

---

## 2. Step-by-Step Connection Instructions

### Step 2.1: Bootstrap the Local Server
1.  Navigate to the repository root directory.
2.  Double-click `run_prototype.bat` to launch the stack on Windows. This automatically sets up the Python virtual environment, installs backend/frontend packages, and launches both services:
    *   **FastAPI Backend API**: `http://127.0.0.1:8000`
    *   **Dashboard Frontend**: `http://localhost:5173`

### Step 2.2: Set Up the Ngrok Tunnel Gateway
Because Microsoft Power Automate runs in the cloud, it cannot access your local server directly. You must expose the backend port:
1.  Download **[ngrok](https://ngrok.com/)**.
2.  Open a terminal window and run:
    ```powershell
    ngrok http 8000
    ```
3.  Copy the secure HTTPS URL from the terminal output (e.g. `https://12ab-34-56-78-90.ngrok-free.app`). Let's refer to this as your **`[TUNNEL_URL]`**.

### Step 2.3: Configure the Power Automate Flow
1.  Open the **[Microsoft Power Automate Portal](https://make.powerautomate.com)**.
2.  Create an **Automated Cloud Flow** triggered by:
    *   `Office 365 Outlook - When a new email arrives (V3)`
3.  Add a **Condition** check:
    *   `Subject` (from trigger output) **contains** the keyword `upload_request`.
4.  Inside the **If yes** branch, add an **Apply to each** loop matching the `Attachments` array.
5.  Inside the loop, add a **Condition** check:
    *   `Name` (attachment file name) **ends with** `.xlsx`.
6.  Inside the loop's **If yes** branch, add a **Data Operation - Compose** block named **`Convert_Attachment_To_Base64`** with the expression:
    ```text
    base64(items('Apply_to_each')?['contentBytes'])
    ```
7.  Add an **HTTP** block named **`HTTP_Webhook`** to post data to your backend:
    *   **Method**: `POST`
    *   **URI**: `[TUNNEL_URL]/api/upload/webhook` *(Replace `[TUNNEL_URL]` with your ngrok HTTPS link)*
    *   **Headers**:
        *   `X-API-KEY`: `PA-Secure-Token-12345`
        *   `Content-Type`: `application/json`
    *   **Body**:
        ```json
        {
          "email_id": "@{triggerOutputs()?['body/id']}",
          "sender": "@{triggerOutputs()?['body/from']}",
          "subject": "@{triggerOutputs()?['body/subject']}",
          "received_time": "@{triggerOutputs()?['body/receivedDateTime']}",
          "attachment_name": "@{items('Apply_to_each')?['name']}",
          "file_content_base64": "@{outputs('Convert_Attachment_To_Base64')}",
          "target_table": "user_activities",
          "target_database": "AUTO",
          "processing_mode": "STRICT"
        }
        ```
8.  Add a second **HTTP** block named **`Reconciliation_Request`** directly following `HTTP_Webhook`:
    *   **Method**: `POST`
    *   **URI**: `[TUNNEL_URL]/api/reconciliation`
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

## 3. Testing the Integration

### 3.1 Setup Target Table in Emulator
1.  Open the dashboard at `http://localhost:5173` and log in (Credentials: `admin` / `admin123`).
2.  Go to the **ClickHouse Engine** tab.
3.  Under **ClickHouse Emulator Tables**, click **Create Table** and select `user_activities` (or `user_data_index`). This sets up a mock target database in your local SQLite store.

### 3.2 Send Ingestion Email
Send an email to your Outlook mailbox with:
*   **Subject**: `upload_request for table: user_activities`
*   **Attachment**: A valid Excel workbook containing columns `id`, `user_id`, `activity`, `timestamp`.

### 3.3 Verify Execution
*   Power Automate will detect the email, convert the Excel file, and hit your ngrok tunnel webhook.
*   The dashboard will register a new Ingestion Job immediately. You can track the state timeline from `EMAIL_RECEIVED` through validation to `COMPLETED` (or `QUARANTINED` if validation failed).
*   Reconciliation runs will match backend counts and confirm success in the **Integration / PA Flow** tab.
