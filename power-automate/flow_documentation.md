# Microsoft Power Automate Ingestion Flow Setup & Documentation

This document provides step-by-step instructions and configuration specifications to implement the Microsoft Power Automate flow that connects Microsoft Outlook emails to the ClickHouse Ingestion Gateway.

---

## 1. Flow Architecture Overview

The flow is designed as an automated cloud workflow triggered by incoming emails in a target Outlook mailbox. It filters out unrelated emails, extracts Excel workbooks, encodes them in base64, passes them to our API webhook, handles the response, reconciles the results, and triggers confirmation emails.

```text
Incoming Email ──► [Outlook Trigger]
                         │
                         ▼
                 [Subject Filter] ── No ──► [Terminate]
                         │
                        Yes
                         ▼
             [Retrieve Excel File]
                         │
                         ▼
             [Base64 Encode Content]
                         │
                         ▼
             [API Webhook Request] ──► Ingestion Job Created (FastAPI)
                         │
                         ▼
             [Reconciliation Check]
                         │
             ┌───────────┴───────────┐
             ▼                       ▼
      [Reconcile Success]     [Reconcile Mismatch/Fail]
             │                       │
             ▼                       ▼
      Send Success Email      Send Failure Email (Quarantine)
```

---

## 2. Trigger Configuration (Outlook V3)

*   **Connector**: `Office 365 Outlook`
*   **Action Trigger**: `When a new email arrives (V3)`
*   **Parameters**:
    *   **Folder**: `Inbox` (or a dedicated subdirectory like `IngestionFeeds`)
    *   **Importance**: `Any`
    *   **Only with Attachments**: `Yes` *(Crucial: prevents empty emails from triggering processing)*
    *   **Include Attachments**: `Yes` *(Enables Power Automate to fetch the file contents in subsequent steps)*

---

## 3. Email Filtering & Parsing Logic

To identify the ClickHouse target table and database from the email, we configure a subject and body check:

### 3.1 Subject Pattern Filter
Add a **Condition** action directly following the trigger:
*   **Left Value**: `Subject` (from trigger output)
*   **Operator**: `contains`
*   **Right Value**: `upload_request`

### 3.2 Target Extraction
We expect the email body or subject to contain explicit mapping parameters, for example:
```text
UPLOAD_REQUEST
TABLE: user_activities
DATABASE: AUTO
MODE: STRICT
END_REQUEST
```

Inside the flow:
1.  Add a **Data Operation - Compose** block named `Extract_Table`.
2.  Use the **Substring** and **IndexOf** expressions to parse the table name from the body, or pass the full subject to let the FastAPI backend perform the regex extraction automatically. 
    *(Recommended: The FastAPI backend automatically parses target tables using rules configured in the dashboard, so forwarding the subject to the backend is the most robust approach).*

---

## 4. Attachment Handling Steps

Since an email may contain multiple attachments (like signatures or images), we loop through them and filter by extension:

1.  Add an **Apply to each** loop. Output from previous step: `Attachments` array from the trigger.
2.  Add a **Condition** inside the loop:
    *   **Left Value**: `Name` (attachment file name)
    *   **Operator**: `ends with`
    *   **Right Value**: `.xlsx`
3.  Inside the "Yes" branch, add a **Data Operation - Compose** block named `Convert_Attachment_To_Base64`.
4.  Set the inputs using the expression:
    ```json
    base64(items('Apply_to_each')?['contentBytes'])
    ```
    *This converts the binary Excel file into a transferrable Base64 text string required by the API JSON payload.*

---

## 5. Webhook HTTP Request Configuration

Inside the attachment loop (after encoding), add an **HTTP** action (rename it to `HTTP_Webhook` for expression compatibility) to trigger the backend ingestion:

*   **Method**: `POST`
*   **URI**: `https://ingestion.company.com/api/upload/webhook`
*   **Headers**:
    *   `X-API-KEY`: `PA-Secure-Token-12345` *(Matches backend POWER_AUTOMATE_API_KEY environment config)*
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
*   **Timeout**: `PT120S` (2 minutes)

---

## 6. Reconciliation Flow

Once the webhook responds, the flow must wait for backend verification.

1.  Add an **HTTP** action named `Reconciliation_Request` to post the reconciliation check:
    *   **Method**: `POST`
    *   **URI**: `https://ingestion.company.com/api/reconciliation`
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
2.  Add a **Condition** action to check the reconciliation status:
    *   **Left Value**: `match_status` (from reconciliation output JSON)
    *   **Operator**: `equals`
    *   **Right Value**: `MATCHED`

---

## 7. Notification Flows (Success & Failure Emails)

### 7.1 Success Email Action (If Matched)
*   **Connector**: `Office 365 Outlook - Send an email (V2)`
*   **To**: `@{triggerOutputs()?['body/from']}` (the original sender)
*   **Subject**: `SUCCESS: Data Ingestion for Table @{body('HTTP_Webhook')?['target_table']} Completed`
*   **Body (HTML)**:
    ```html
    <p>Hello,</p>
    <p>The attachment <b>@{items('Apply_to_each')?['name']}</b> has been successfully ingested.</p>
    <ul>
      <li><b>Job ID</b>: @{body('HTTP_Webhook')?['id']}</li>
      <li><b>Target</b>: @{body('HTTP_Webhook')?['target_database']}.@{body('HTTP_Webhook')?['target_table']}</li>
      <li><b>Rows Inserted</b>: @{body('HTTP_Webhook')?['inserted_rows']}</li>
    </ul>
    <p>Best regards,<br/>Ingestion Service</p>
    ```

### 7.2 Failure Email Action (If Mismatched or Webhook Failed)
*   **Connector**: `Office 365 Outlook - Send an email (V2)`
*   **To**: `@{triggerOutputs()?['body/from']}; admin@company.com`
*   **Subject**: `FAILURE: Ingestion Rejected for Table @{triggerOutputs()?['body/subject']}`
*   **Body (HTML)**:
    ```html
    <p>Hello,</p>
    <p>The attachment ingestion failed schema validation or row type checks. <b>ZERO rows were inserted.</b></p>
    <p>The file has been quarantined for review. Please inspect details in the Ingestion Dashboard.</p>
    <ul>
      <li><b>Job ID</b>: @{body('HTTP_Webhook')?['id']}</li>
      <li><b>Error details</b>: @{body('HTTP_Webhook')?['error_summary']}</li>
    </ul>
    ```

---

## 8. Error Handling & Retry Policies

*   **Webhook Timeout**: Set the HTTP Webhook `Retry Policy` to `None` inside Settings. If the gateway server is down, Power Automate will fail immediately. This prevents half-inserted loops.
*   **Run After Settings**: Configure the Ingestion Failure Email block's `Run After` property to trigger if the HTTP Webhook action **fails**, **times out**, or is **skipped**. This ensures you are notified even if the API server crashes.
*   **Duplicate Submissions**: The backend checks attachment hashes. If the same attachment is processed twice, the backend webhook will reject it, and Power Automate will send a duplicate alert email instead of double-inserting data.

---

## 9. Security Recommendations for Production

1.  **HTTPS Enforcement**: All webhooks must target secure TLS endpoints (`https://`).
2.  **API Key Rotation**: Use Power Automate **Environment Variables** to store the `X-API-KEY` header value, allowing secret rotation without modifying flow blocks.
3.  **Tenant Isolation**: Restrict the flow to trigger only from internal tenant senders (e.g. `*@yourcompany.com`) to prevent external spam attacks.
