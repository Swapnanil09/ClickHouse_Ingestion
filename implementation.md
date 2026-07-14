You are a senior software architect, senior Python/FastAPI engineer, senior React/Next.js engineer, DevOps engineer, data engineer, Microsoft Power Platform expert, ClickHouse expert, security engineer, and expert UI/UX product designer.

Your task is to DESIGN AND BUILD a complete, production-oriented, dynamic Outlook-to-ClickHouse automated data ingestion, schema validation, monitoring, and audit platform.

Do not build a toy demo, static mockup, or hardcoded proof of concept.

Build a modular, extensible, secure, observable, and production-oriented application.

# 1. PRODUCT VISION

The product is a web-based dynamic data ingestion platform.

The core workflow is:

Outlook Email
→ Microsoft Power Automate
→ Detect relevant incoming email
→ Detect Excel attachment
→ Read email configuration/metadata
→ Obtain explicitly provided ClickHouse target table name
→ Send or make the attachment available to the application backend
→ Create an ingestion job
→ Dynamically inspect the Excel workbook
→ Detect all sheets
→ Detect headers
→ Collect column names
→ Infer data types
→ Count rows
→ Connect to the configured ClickHouse instance
→ Dynamically search databases for the explicitly provided target table
→ Identify the target database/table
→ Retrieve the actual ClickHouse table schema
→ Validate Excel schema against ClickHouse schema
→ Validate data types and row values
→ If validation fails, insert ZERO rows, create a detailed failure report, log the failure, update the dashboard, quarantine the file, and send a failure email
→ If validation passes, insert the data into ClickHouse in configurable batches
→ Verify the ingestion result
→ Store audit information
→ Update the dashboard
→ Send a success email
→ Use Microsoft Power Automate as an additional workflow/integration verification layer to check that the job/file/status/count information exposed in the dashboard/backend matches the information processed through the Power Automate workflow
→ Report discrepancies instead of silently ignoring them.

The system must be dynamic.

Do not hardcode:

* Outlook email addresses
* Email subjects
* Attachment names
* Excel filenames
* Excel sheet names
* Excel column names
* ClickHouse database names
* ClickHouse table names
* ClickHouse schemas
* Row counts
* File locations
* Production URLs
* Secrets
* Credentials

All appropriate configuration must come from environment variables, application settings, user configuration, workflow configuration, or dynamically discovered metadata.

# 2. IMPORTANT TARGET TABLE RULE

The system MUST NOT use AI or automatic guessing to determine the destination ClickHouse table.

The target table name must be explicitly provided.

Support configurations such as:

UPLOAD_REQUEST

TABLE: user_activities
DATABASE: AUTO
MODE: STRICT

END_REQUEST

Also design support for multiple Excel sheets:

UPLOAD_REQUEST

MODE: STRICT

SHEET: Users
TABLE: user_data_index

SHEET: Activities
TABLE: user_activities

END_REQUEST

The system should support:

1. Explicit database + table.
2. Table name with DATABASE=AUTO.
3. Multiple sheet-to-table mappings.

If DATABASE=AUTO:

* Search only authorized/configured ClickHouse databases.
* If exactly one matching table exists, continue.
* If zero matching tables exist, fail safely.
* If multiple tables with the same name exist across databases, fail safely and request explicit database information.
* Never arbitrarily choose a database.

# 3. MICROSOFT POWER AUTOMATE INTEGRATION

Microsoft Power Automate must be included in the architecture.

Design the integration carefully.

Power Automate should be responsible for workflow orchestration tasks such as:

* Detecting relevant Outlook emails.
* Filtering emails based on configurable conditions.
* Detecting attachments.
* Retrieving Excel attachments.
* Passing job metadata to the backend.
* Calling secured backend API endpoints.
* Receiving processing results.
* Sending success notifications.
* Sending failure notifications.
* Performing an additional reconciliation/verification check.

The backend application must remain the source of truth for:

* File processing.
* Excel inspection.
* Schema discovery.
* Validation.
* ClickHouse insertion.
* Ingestion state.
* Audit logs.
* Row counts.
* Error reports.

Implement a Power Automate reconciliation mechanism.

After processing, Power Automate should call a secured reconciliation/status endpoint.

The reconciliation logic should compare appropriate fields such as:

* ingestion_job_id
* email/message identifier
* attachment identifier or hash
* filename
* target database
* target table
* expected row count
* validated row count
* inserted row count
* failed row count
* backend status
* workflow status
* timestamps where appropriate

If there is a mismatch:

* Do not silently ignore it.
* Create a reconciliation failure/discrepancy record.
* Display it prominently on the dashboard.
* Log the mismatch.
* Send an appropriate alert/notification.

Do not make Power Automate query the visual dashboard UI to compare values.

Use secure backend API endpoints and persisted audit records for reconciliation.

Create documentation explaining exactly how to configure the Power Automate flow.

# 4. OUTLOOK AND EMAIL WORKFLOW

Implement or architect the Outlook integration so the application can work reliably with Microsoft Power Automate.

Each incoming ingestion request should capture:

* Email/message ID.
* Sender.
* Recipient where available.
* Subject.
* Received timestamp.
* Attachment name.
* Attachment size.
* Attachment hash.
* Target table.
* Optional target database.
* Processing mode.
* Sheet mappings where applicable.
* Power Automate workflow/run identifier if available.

Prevent duplicate processing.

# 5. IDEMPOTENCY

Idempotency is mandatory.

Generate or store a reliable idempotency identifier based on appropriate values such as:

* Email message ID.
* Attachment hash.
* Sheet name.
* Target database.
* Target table.

The exact implementation should be well-designed and documented.

Before inserting data, check whether the same ingestion unit has already completed successfully.

Prevent accidental duplicate ClickHouse insertion.

Handle scenarios such as:

* Power Automate retries the HTTP request.
* The backend receives the same request twice.
* The same email is processed twice.
* The application crashes after ClickHouse insertion but before updating the job status.
* A user manually retries a job.

# 6. INGESTION JOB STATE MACHINE

Every ingestion request must create a trackable job.

Implement a robust state machine.

Suggested states:

EMAIL_RECEIVED
ATTACHMENT_RECEIVED
JOB_CREATED
FILE_STORED
EXCEL_PROFILING
EXCEL_PROFILED
TABLE_SEARCHING
TABLE_FOUND
SCHEMA_VALIDATING
SCHEMA_VALIDATED
DATA_VALIDATING
DATA_VALIDATED
READY_TO_INSERT
INSERTING
VERIFYING
RECONCILING
COMPLETED
FAILED
QUARANTINED
RETRYING
CANCELLED

Design valid state transitions.

Prevent invalid state transitions.

Persist state transition history.

Every transition should store:

* Previous state.
* New state.
* Timestamp.
* Reason.
* Actor/service.
* Correlation ID where applicable.

# 7. DYNAMIC EXCEL PROCESSING ENGINE

Build a dynamic Excel processing engine.

It should:

* Accept XLSX files.
* Be architected for future CSV support.
* Detect all workbook sheets.
* Detect empty sheets.
* Detect header rows where possible.
* Detect duplicate column names.
* Normalize headers carefully without losing the original names.
* Collect original column names.
* Infer data types.
* Count rows.
* Count columns.
* Detect empty/null values.
* Detect duplicate rows where configured.
* Generate sample data for dashboard preview.
* Generate workbook metadata.
* Generate sheet metadata.

Do not assume the header is always on row 1.

Do not load unnecessarily huge files fully into memory where avoidable.

Design for large-file processing.

Use appropriate techniques such as:

* Streaming/read-only workbook processing where applicable.
* Chunking.
* Batch processing.
* Temporary file management.
* Configurable limits.
* Resource cleanup.

# 8. CLICKHOUSE CONNECTION MANAGEMENT

Build a secure ClickHouse connection management module.

The dashboard should allow authorized users to configure/test a ClickHouse connection.

Support configuration fields such as:

* Connection name.
* Host.
* Port.
* Username.
* Password.
* Secure/TLS option.
* Database restrictions.
* Connection timeout.
* Query timeout where appropriate.

Never expose passwords after storage.

Never log credentials.

Use environment variables or a secure secret-management architecture for production.

Implement:

* Test connection.
* Discover databases.
* Restrict allowed databases.
* Search for provided table names.
* Fetch table schema.
* Fetch column names.
* Fetch ClickHouse data types.
* Fetch nullable/default information.
* Refresh metadata.
* Cache metadata appropriately.

Do not retrieve every column from every table on every email.

Use lazy metadata discovery and caching.

# 9. VALIDATION ENGINE

Implement validation in multiple layers.

## Layer 1: File Validation

Check:

* File exists.
* Supported extension.
* Valid Excel file.
* File is readable.
* File is not empty.
* Workbook contains sheets.
* Selected sheet exists.
* Header can be identified.
* No dangerous/unexpected file conditions.
* File size limits.

## Layer 2: Table Discovery Validation

Check:

* Target table is provided.
* Database is valid if explicitly provided.
* Target table exists.
* AUTO database search returns exactly one valid result.
* User/workflow has permission to use the target database/table.

## Layer 3: Schema Validation

Compare:

Excel columns
vs.
ClickHouse columns.

Detect:

* Matching columns.
* Missing required columns.
* Unexpected columns.
* Nullable columns.
* Non-nullable columns.
* Columns with defaults.
* Materialized/alias columns where relevant.
* Type compatibility.

Support configurable validation modes.

STRICT mode:

* Reject unexpected columns unless explicitly configured.
* Reject missing required columns.
* Reject incompatible types.

Design the architecture so other modes can be added later.

## Layer 4: Data Type Validation

Validate actual values.

Support important ClickHouse types, including:

* String
* FixedString where appropriate
* UInt8/16/32/64
* Int8/16/32/64
* Float32/64
* Decimal
* Date
* DateTime
* DateTime64
* Boolean-compatible values
* Nullable
* LowCardinality
* Array where reasonably possible

Design the type system to be extensible.

## Layer 5: Row Validation

Identify:

* Row number.
* Column name.
* Expected type.
* Actual value or safe representation.
* Error reason.

Do not expose sensitive row values unnecessarily in logs or UI.

# 10. ALL-OR-NOTHING SAFETY RULE

For the initial version, implement:

IF VALIDATION FAILS:
INSERT ZERO ROWS.

Do not partially insert a file when strict validation fails.

Generate:

* Failure job.
* Failure report.
* Error row report where applicable.
* Quarantine record.
* Audit log.
* Failure notification.

# 11. CLICKHOUSE INSERTION ENGINE

If all required validation passes:

* Prepare data safely.
* Convert data to compatible ClickHouse types.
* Insert using configurable batches.
* Track batch progress.
* Track inserted row counts.
* Track failures.
* Support retries carefully.
* Avoid duplicate insertion.
* Verify results where reasonably possible.

The loader should not simply create one enormous pandas DataFrame and blindly insert everything.

Design for configurable batching.

For example:

* Batch size configuration.
* Processing progress.
* Current batch.
* Total batches.
* Rows processed.
* Rows inserted.
* Time elapsed.
* Estimated completion where practical.

# 12. DRY RUN MODE

Implement DRY_RUN mode.

The entire pipeline should execute:

Email
→ Attachment
→ Excel inspection
→ Table discovery
→ Schema validation
→ Data validation
→ Report generation

Then stop before insertion.

The dashboard must clearly indicate DRY_RUN jobs.

# 13. QUARANTINE AND RETRY SYSTEM

Failed files must not simply disappear.

Implement quarantine.

Store or reference:

* Original file.
* Email metadata.
* Job metadata.
* Validation report.
* Error report.
* Failure reason.
* Target database/table.
* Timestamps.

The dashboard should allow authorized users to:

* Inspect failed jobs.
* Inspect errors.
* Retry eligible jobs.
* Cancel jobs.
* Download or access reports.
* View retry history.

Retry logic must respect idempotency.

# 14. AUDIT SYSTEM

Implement detailed auditability.

Store:

* Job ID.
* Correlation ID.
* Email ID.
* Sender.
* Attachment metadata.
* Attachment hash.
* Sheet name.
* Target database.
* Target table.
* Excel columns.
* ClickHouse columns.
* Validation results.
* Total rows.
* Valid rows.
* Invalid rows.
* Inserted rows.
* Processing duration.
* Current status.
* State history.
* Error summary.
* Retry count.
* Reconciliation status.
* Power Automate identifiers where available.
* Created timestamp.
* Updated timestamp.

# 15. DASHBOARD REQUIREMENTS

The UI must look like it was designed by an expert enterprise SaaS UI/UX product designer.

Do not create a generic beginner admin dashboard.

Do not create a cluttered interface.

Do not overuse gradients, glassmorphism, huge cards, excessive rounded corners, random colors, or unnecessary animations.

The UI should be:

* Modern.
* Professional.
* Clean.
* Dense enough for a data engineering platform.
* Easy to scan.
* Accessible.
* Responsive.
* Consistent.
* Production-oriented.
* Suitable for enterprise demonstrations.

Use a coherent design system.

Implement:

* Typography hierarchy.
* Spacing system.
* Reusable components.
* Consistent status colors.
* Accessible contrast.
* Keyboard accessibility where appropriate.
* Loading states.
* Empty states.
* Error states.
* Skeleton loaders.
* Toast notifications.
* Confirmation dialogs.
* Helpful tooltips.
* Responsive tables.
* Filtering.
* Sorting.
* Search.
* Pagination.
* Date filters.

Support dark mode and light mode if practical.

# 16. DASHBOARD PAGES

Implement at least:

## Login / Authentication

Production-oriented authentication architecture.

## Overview

Display:

* Total ingestion jobs.
* Successful jobs.
* Failed jobs.
* Processing jobs.
* Quarantined jobs.
* Reconciliation discrepancies.
* Total processed rows.
* Total inserted rows.
* Recent jobs.
* Success rate.
* Processing trends.
* Failure trends.

## Ingestion Jobs

Table containing:

* Job ID.
* Email.
* Attachment.
* Sheet.
* Database.
* Table.
* Total rows.
* Inserted rows.
* Status.
* Mode.
* Reconciliation status.
* Created time.
* Duration.
* Actions.

## Job Details

Display:

* Email metadata.
* Attachment metadata.
* Job timeline.
* State transitions.
* Excel schema.
* ClickHouse schema.
* Side-by-side schema comparison.
* Validation results.
* Row errors.
* Batch progress.
* Insert statistics.
* Logs.
* Reconciliation information.
* Retry action.
* Cancel action where valid.
* Report access.

## Outlook / Power Automate Integration

Display:

* Integration status.
* Configuration instructions.
* Last webhook/event.
* Recent workflow requests.
* Power Automate reconciliation status.
* Integration errors.

## ClickHouse Connections

Display:

* Configured connections.
* Connection status.
* Test connection.
* Allowed databases.
* Metadata refresh.
* Last schema refresh.

## Workflow Configuration

Allow configuration of:

* Email rules.
* Sender rules.
* Subject rules.
* Attachment rules.
* Target extraction rules.
* Processing mode.
* Database restrictions.
* Notification behavior.

## Quarantine

Display:

* Failed files.
* Failure reasons.
* Validation reports.
* Retry eligibility.
* Retry history.

## Reports

Display:

* Success/failure trends.
* Processing performance.
* Row statistics.
* Top failure reasons.
* Reconciliation mismatches.

## Audit Logs

Searchable/filterable audit records.

## Settings

System configuration appropriate for the platform.

# 17. REAL-TIME OR NEAR-REAL-TIME DASHBOARD UPDATES

Implement an appropriate mechanism for job progress updates.

Choose and justify one of:

* WebSockets.
* Server-Sent Events.
* Polling with sensible intervals.

The UI should reflect job state and batch progress without requiring constant manual refresh.

# 18. RECOMMENDED TECHNOLOGY STACK

Use an appropriate production-oriented stack.

Preferred:

Frontend:

* Next.js or React.
* TypeScript.
* A maintainable component architecture.
* An appropriate UI component system.
* Professional charting solution where needed.

Backend:

* Python.
* FastAPI.
* Pydantic.
* SQLAlchemy or another justified persistence approach.
* Alembic migrations.

Processing:

* pandas where appropriate.
* openpyxl where appropriate.
* Memory-conscious processing techniques.

ClickHouse:

* clickhouse-connect or another well-justified Python client.

Metadata/Audit Database:

* PostgreSQL for production.
* SQLite may be supported only for easy local development.

Background Jobs:
Choose and justify an architecture such as:

* Celery + Redis.
* Dramatiq.
* RQ.
* Another reliable job-processing approach.

Do not process huge Excel files synchronously inside a normal HTTP request.

Infrastructure:

* Docker.
* Docker Compose for local development.
* Reverse proxy architecture for production.
* Environment-based configuration.

# 19. SECURITY REQUIREMENTS

Implement and document:

* Authentication.
* Authorization/RBAC.
* Secure credential storage.
* Secret management.
* No secrets committed to Git.
* .env.example.
* Input validation.
* File upload restrictions.
* File size limits.
* MIME/type validation.
* Safe filename handling.
* Temporary file cleanup.
* API authentication between Power Automate and backend.
* Webhook/API request verification.
* Rate limiting.
* CORS configuration.
* CSRF considerations where relevant.
* SQL/query safety.
* ClickHouse least-privilege account recommendations.
* Database restrictions.
* Audit logs.
* Sensitive data masking.
* Secure HTTP headers.
* TLS/HTTPS requirements.
* Dependency security.
* Container security.
* Backup strategy.
* Recovery strategy.

# 20. OBSERVABILITY

Implement production-oriented observability.

Include:

* Structured logging.
* Correlation IDs.
* Job IDs in logs.
* Appropriate log levels.
* Error tracking architecture.
* Metrics.
* Health endpoints.
* Readiness endpoint.
* Liveness endpoint.
* Dependency health checks.
* ClickHouse connectivity checks.
* PostgreSQL checks.
* Redis/worker checks if used.

Design for future integration with tools such as:

* Prometheus.
* Grafana.
* OpenTelemetry.
* Sentry or equivalent.

# 21. ERROR HANDLING

Never return meaningless errors such as:

"Something went wrong."

Implement useful error codes/categories.

Examples:

EXCEL_INVALID
EXCEL_EMPTY
HEADER_NOT_FOUND
DUPLICATE_COLUMNS
TABLE_NAME_MISSING
DATABASE_NOT_FOUND
TABLE_NOT_FOUND
MULTIPLE_TABLE_MATCHES
SCHEMA_MISMATCH
TYPE_VALIDATION_FAILED
ROW_VALIDATION_FAILED
CLICKHOUSE_CONNECTION_FAILED
CLICKHOUSE_INSERT_FAILED
DUPLICATE_INGESTION
POWER_AUTOMATE_AUTH_FAILED
RECONCILIATION_MISMATCH
INTERNAL_PROCESSING_ERROR

Errors should contain:

* Safe user-facing message.
* Internal error code.
* Correlation ID.
* Timestamp.
* Appropriate technical context in secure logs.

# 22. TESTING REQUIREMENTS

Implement meaningful tests.

Include:

* Unit tests.
* Integration tests.
* API tests.
* Excel parsing tests.
* Schema validation tests.
* ClickHouse type conversion tests.
* State transition tests.
* Idempotency tests.
* Retry tests.
* Reconciliation tests.
* Failure-path tests.

Test important scenarios:

* Valid Excel.
* Invalid Excel.
* Empty workbook.
* Multiple sheets.
* Missing table.
* Multiple database table matches.
* Missing columns.
* Extra columns.
* Invalid types.
* Null in non-nullable field.
* Duplicate email delivery.
* Duplicate Power Automate request.
* Retry after failure.
* Crash/recovery scenario.
* ClickHouse unavailable.
* Metadata database unavailable.
* Worker failure.
* Reconciliation mismatch.

# 23. PROJECT STRUCTURE

Create a clean monorepo or clearly organized repository.

Example:

project-root/

frontend/

backend/

infrastructure/

power-automate/

docs/

tests/

scripts/

docker-compose.yml

.env.example

README.md

SETUP_GUIDE.md

PRODUCTION_PITCH.md

Do not put the entire backend into one Python file.

Use separation of concerns.

Example backend modules:

* api
* auth
* config
* models
* schemas
* repositories
* services
* workers
* excel
* clickhouse
* validation
* ingestion
* notifications
* reconciliation
* audit
* observability

# 24. API DESIGN

Design clean REST APIs.

Include appropriate endpoints for:

* Authentication.
* Dashboard statistics.
* Ingestion jobs.
* Job details.
* Job retry.
* Job cancellation.
* Power Automate ingestion request.
* Power Automate reconciliation.
* ClickHouse connections.
* Test connection.
* Database discovery.
* Table discovery.
* Schema discovery.
* Workflow configuration.
* Quarantine.
* Reports.
* Audit logs.
* Health/readiness/liveness.

Provide OpenAPI documentation through FastAPI.

# 25. DATABASE DESIGN

Design PostgreSQL tables/models for appropriate entities such as:

* users
* roles
* clickhouse_connections
* allowed_databases
* workflow_configs
* ingestion_jobs
* ingestion_units
* attachments
* workbook_sheets
* detected_columns
* validation_runs
* validation_errors
* insertion_batches
* job_state_history
* quarantine_records
* retry_attempts
* reconciliation_runs
* reconciliation_discrepancies
* audit_logs

Use proper:

* Primary keys.
* Foreign keys.
* Indexes.
* Unique constraints.
* Timestamps.
* Status fields.
* JSON fields only where justified.

# 26. MICROSOFT POWER AUTOMATE DELIVERABLES

Create a dedicated power-automate directory.

Include:

* Flow architecture documentation.
* Trigger configuration.
* Outlook email filtering logic.
* Attachment handling steps.
* HTTP request configuration.
* Authentication configuration.
* Backend payload examples.
* Response handling.
* Success email flow.
* Failure email flow.
* Reconciliation flow.
* Retry behavior.
* Error handling.
* Environment-specific configuration.
* Production security recommendations.

If exporting a Power Automate flow package is not technically possible from the development environment, create exact step-by-step implementation documentation sufficient for a developer/administrator to reproduce the flow.

# 27. REQUIRED MARKDOWN DOCUMENTATION

You MUST create exactly these three primary Markdown documentation files at the repository root:

1. README.md
2. SETUP_GUIDE.md
3. PRODUCTION_PITCH.md

Additional technical documentation may exist inside docs/ and power-automate/, but these three root documents are mandatory.

# 28. README.md REQUIREMENTS

README.md must include:

* Project name.
* Product overview.
* Problem statement.
* Solution.
* Key features.
* Architecture overview.
* Architecture diagram using Mermaid.
* Complete workflow.
* Technology stack.
* Repository structure.
* Main components.
* Dashboard features.
* Outlook/Power Automate integration overview.
* Excel processing overview.
* ClickHouse discovery.
* Validation process.
* Insertion process.
* Idempotency.
* Quarantine.
* Reconciliation.
* Security overview.
* Observability overview.
* Local quick start.
* API documentation location.
* Testing instructions.
* Screenshots section/placeholders where appropriate.
* Limitations.
* Roadmap.
* Contribution/development guidance.

The README must be useful to both technical and non-technical readers.

# 29. SETUP_GUIDE.md REQUIREMENTS

SETUP_GUIDE.md must be extremely detailed.

It must contain everything required to run this application locally, in staging, and in production.

Include:

* Prerequisites.
* Supported operating systems.
* Required software.
* Python version.
* Node version.
* Docker requirements.
* PostgreSQL requirements.
* Redis requirements if used.
* ClickHouse requirements.
* Microsoft/Outlook requirements.
* Power Automate requirements.
* Repository cloning.
* Environment variable setup.
* .env configuration.
* Frontend setup.
* Backend setup.
* Database creation.
* Database migrations.
* Worker setup.
* ClickHouse account setup.
* Least-privilege ClickHouse permissions.
* Power Automate setup.
* Exact Power Automate flow steps.
* API authentication setup.
* Local development.
* Docker Compose deployment.
* Staging deployment.
* Production deployment architecture.
* Reverse proxy configuration guidance.
* Domain setup.
* DNS considerations.
* TLS/HTTPS setup.
* Certificate renewal.
* Secret management.
* PostgreSQL production configuration.
* Redis production configuration.
* Worker scaling.
* Backend scaling.
* Frontend scaling.
* ClickHouse connection security.
* Firewall/networking.
* Rate limiting.
* CORS.
* CSRF considerations.
* Security headers.
* Backup configuration.
* PostgreSQL backups.
* Application file/quarantine backups.
* Disaster recovery.
* Restore procedures.
* Logging.
* Log rotation.
* Metrics.
* Monitoring.
* Alerting.
* Health checks.
* Readiness/liveness probes.
* OpenTelemetry recommendations.
* Prometheus recommendations.
* Grafana recommendations.
* Error tracking.
* CI/CD.
* GitHub Actions or equivalent pipeline.
* Automated tests.
* Security scanning.
* Dependency scanning.
* Container scanning.
* Image registry.
* Deployment process.
* Rollback process.
* Zero/minimal downtime deployment considerations.
* Database migration strategy.
* Production checklist.
* Go-live checklist.
* Post-deployment verification.
* Troubleshooting.
* Common errors.
* Performance tuning.
* Large Excel file considerations.
* ClickHouse insertion tuning.
* PostgreSQL tuning.
* Worker tuning.
* Capacity planning.
* Horizontal scaling.
* High availability recommendations.
* Upgrade procedures.
* Maintenance procedures.
* Incident response considerations.

Do not write vague statements such as "configure security appropriately."

Give actionable production guidance.

# 30. PRODUCTION_PITCH.md REQUIREMENTS

PRODUCTION_PITCH.md should be written as a presentation/pitch document suitable for showing management, technical leadership, engineering teams, or potential stakeholders.

Structure it like a professional presentation.

Include:

* Title slide.
* Executive summary.
* Current problem.
* Pain points.
* Existing manual workflow.
* Business impact.
* Proposed solution.
* Product vision.
* How the system works.
* Architecture.
* Outlook and Power Automate integration.
* Dynamic Excel processing.
* ClickHouse schema validation.
* Safety mechanisms.
* Zero-row insertion on validation failure.
* Idempotency.
* Quarantine and retry.
* Reconciliation.
* Dashboard capabilities.
* Auditability.
* Security.
* Scalability.
* Reliability.
* Observability.
* Operational benefits.
* Engineering benefits.
* Business benefits.
* Risk reduction.
* Time savings.
* Error reduction.
* Production readiness.
* Deployment model.
* Implementation phases.
* V1 scope.
* V2 roadmap.
* Future AI-assisted capabilities.
* KPIs and success metrics.
* Risks and mitigations.
* Cost considerations.
* Expected ROI framework.
* Why this solution should be adopted.
* Final recommendation.
* Closing slide.

Use Mermaid diagrams and tables where useful.

The pitch should not overpromise unsupported financial savings.

Use measurable KPI frameworks rather than invented numbers.

# 31. IMPLEMENTATION PHASES

Build the project incrementally.

Phase 1:

* Repository architecture.
* Backend foundation.
* Frontend foundation.
* PostgreSQL.
* Authentication.
* Basic dashboard.

Phase 2:

* ClickHouse connection management.
* Database/table discovery.
* Schema retrieval.

Phase 3:

* Excel upload/processing.
* Dynamic workbook profiling.
* Validation engine.

Phase 4:

* Ingestion job system.
* Background workers.
* State machine.
* Idempotency.

Phase 5:

* Batch ClickHouse insertion.
* Verification.
* Quarantine.
* Retry.

Phase 6:

* Power Automate integration.
* Secure API endpoints.
* Notifications.
* Reconciliation.

Phase 7:

* Advanced dashboard.
* Reports.
* Audit logs.
* Real-time updates.

Phase 8:

* Security hardening.
* Observability.
* Testing.
* Docker/infrastructure.
* Production documentation.

# 32. DEVELOPMENT BEHAVIOR

Before coding:

1. Analyze all requirements.
2. Design the architecture.
3. Decide the final technology stack.
4. Explain important architectural decisions.
5. Create an implementation plan.
6. Create the repository structure.
7. Then begin implementation.

While coding:

* Do not leave critical features as TODO comments.
* Do not use fake implementations for core functionality.
* Do not hardcode demo data into production paths.
* Do not create frontend pages disconnected from backend functionality.
* Do not silently catch exceptions.
* Do not expose secrets.
* Do not put huge business logic inside API routes.
* Do not process large files synchronously in request handlers.
* Do not allow invalid state transitions.
* Do not allow duplicate ingestion.
* Do not insert data before validation succeeds.
* Do not claim production readiness for features that are not implemented.

If a feature cannot be fully implemented because of external credentials, Microsoft tenant access, Power Automate environment access, or unavailable infrastructure:

1. Implement the complete internal interface and integration boundary.
2. Implement mocks only for tests/development where appropriate.
3. Clearly document what external configuration is required.
4. Provide exact setup steps.
5. Do not pretend the external integration was tested if it was not.

# 33. CODE QUALITY

Follow:

* SOLID principles where useful.
* Clean architecture principles without unnecessary overengineering.
* Type hints.
* Clear naming.
* Modular design.
* Dependency injection where appropriate.
* Reusable services.
* Repository/service separation.
* Centralized configuration.
* Centralized exception handling.
* Structured logging.
* Consistent API responses.
* Database migrations.
* Testable code.

# 34. UI/UX QUALITY CONTROL

Before considering the frontend complete, inspect every page as an expert SaaS UI/UX designer.

Ask:

* Is the information hierarchy clear?
* Can an operator understand system health in seconds?
* Can failed jobs be identified immediately?
* Are dangerous actions clearly differentiated?
* Is schema comparison easy to understand?
* Are errors actionable?
* Are tables readable with large datasets?
* Are empty states useful?
* Are loading states professional?
* Is the interface responsive?
* Is the interface accessible?
* Does the design look like a serious data engineering/enterprise product?

Refine the UI until the answer is yes.

# 35. FINAL ACCEPTANCE CRITERIA

The application should demonstrate this complete workflow:

1. User opens the dashboard.
2. User configures ClickHouse.
3. User tests the connection.
4. System dynamically discovers authorized databases.
5. User configures Outlook/Power Automate workflow.
6. An email arrives with an Excel attachment and explicit target table information.
7. Power Automate detects the email.
8. Power Automate securely sends metadata/file information to the backend.
9. Backend creates an ingestion job.
10. Backend prevents duplicate ingestion.
11. Backend stores and profiles the Excel file.
12. Backend collects dynamic sheets and columns.
13. Backend finds the provided table in ClickHouse.
14. Backend fetches the actual ClickHouse schema.
15. Backend validates the Excel schema.
16. Backend validates data types.
17. Backend validates rows.
18. If validation fails, ZERO rows are inserted.
19. A detailed report is generated.
20. The file/job is quarantined.
21. The dashboard shows the failure.
22. A failure email is sent through the workflow.
23. If validation passes, data is inserted in configurable batches.
24. Progress is visible in the dashboard.
25. The insertion result is verified.
26. Audit data is stored.
27. Power Automate performs reconciliation through the secured backend endpoint.
28. Any discrepancy is prominently reported.
29. The dashboard shows final job status.
30. A success notification is sent.
31. The complete history remains auditable.

# 36. FINAL DELIVERABLE

Deliver:

* Complete frontend source code.
* Complete backend source code.
* PostgreSQL models and migrations.
* Background worker implementation.
* Dynamic Excel processing.
* Dynamic ClickHouse discovery.
* Validation engine.
* Batch insertion.
* Idempotency.
* State machine.
* Quarantine.
* Retry system.
* Power Automate integration endpoints.
* Reconciliation.
* Dashboard.
* Authentication/authorization.
* Audit logs.
* Tests.
* Docker setup.
* Docker Compose.
* .env.example.
* Infrastructure guidance.
* Power Automate implementation documentation.
* README.md.
* SETUP_GUIDE.md.
* PRODUCTION_PITCH.md.

Start by analyzing the requirements and presenting the architecture and implementation plan.

Then create the project systematically phase by phase.

Do not stop after generating only an architecture proposal or UI mockup.

Continue until the complete project structure, implementation, tests, configuration, and all required documentation are created.
