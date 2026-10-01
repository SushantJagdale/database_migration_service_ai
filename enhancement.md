# Database Migration Service (DMS) AI — Enhancements Tracker (`dms-enhance`)

This document tracks all architectural, agentic, API, and UI enhancements implemented on the `dms-enhance` branch (branched from `dms-adk2`) for homogeneous database discovery and migration from **AWS RDS / Aurora** to **Google Cloud SQL**.

---

## Status Summary

| # | Enhancement Area | Status | Key Files Modified |
|---|---|---|---|
| 1 | **Automated DMS Error Diagnosis & Resolution (`FULL_DUMP` & `CDC`)** | Completed | `backend/root_agent/dbmigration/dbmigration_agent.py`, `backend/main.py`, `frontend/templates/index.html` |
| 2 | **Unified Smart `Check DMS Status` & Self-Healing Controls (`Resume`, `Restart`)** | Completed | `backend/root_agent/dbmigration/dbmigration_agent.py`, `backend/main.py`, `frontend/main.py`, `frontend/templates/index.html` |
| 3 | **Pre-Promotion Safety Gate (Cutover Guardrails)** | Completed | `backend/root_agent/dbmigration/dbmigration_agent.py` |
| 4 | **Deep Pre-Migration Readiness & Schema-Level Checks (MySQL & PostgreSQL)** | Completed | `backend/root_agent/mysql/mysql_agent.py`, `backend/root_agent/postgres/postgres_agent.py` |
| 5 | **AWS Aurora Cluster Parameter Support & CloudWatch Right-Sizing Telemetry** | Completed | `backend/root_agent/aws_utils.py`, `backend/root_agent/mysql/mysql_agent.py`, `backend/root_agent/postgres/postgres_agent.py` |
| 6 | **Interactive Remediation Commands in HTML Pre-Migration Reports** | Completed | `backend/root_agent/report_generator.py` |
| 7 | **Source-vs-Target Data Parity Validation (Row Counts, Deltas, Sequences)** | Completed | `backend/database_validator.py`, `frontend/templates/index.html` |
| 8 | **Cloud Run Deployment, Frontend Reverse Proxy & Terraform IAM** | Completed | `frontend/main.py`, `backend/Dockerfile`, `frontend/Dockerfile`, `terraform/main.tf` |

---

## Detailed Enhancements

### 1. Automated DMS Error Diagnosis & Resolution (`FULL_DUMP` & `CDC`)
* **Files**:
  * `backend/root_agent/dbmigration/dbmigration_agent.py` (`fetch_dms_job_logs`, `analyze_dms_error_and_suggest_resolution`, `get_dms_job_structured_status`)
  * `frontend/templates/index.html` (`renderErrorAdvisor`)
* **What Changed**:
  * Added `fetch_dms_job_logs()` to query Google Cloud Logging (`resource.type="datamigration.googleapis.com/MigrationJob"` and `resource.type="cloudsql_database"`) for recent `WARNING` and `ERROR` logs associated with the DMS migration job and Cloud SQL replica.
  * Added `analyze_dms_error_and_suggest_resolution()` to classify errors occurring during `FULL_DUMP`, `CDC`, or connection setup into actionable remediation plans with root cause, step-by-step instructions, copy-pasteable SQL / AWS CLI scripts, and a recommended recovery action (`verify`, `resume`, or `restart`).
  * **Covered Error Categories**:
    1. **MySQL Error 1236 (`ER_MASTER_FATAL_ERROR_READING_BINLOG`)**: Binary logs purged on RDS before CDC could read them -> recommends `CALL mysql.rds_set_configuration('binlog retention hours', 72);` and `restart`.
    2. **MySQL Error 1153 (`ER_NET_PACKET_TOO_LARGE`)**: Row or binlog packet exceeds `max_allowed_packet` during `FULL_DUMP` or `CDC` -> recommends increasing `max_allowed_packet` to `536870912` (512MB) and `resume`.
    3. **Database Auth / Privilege Failures (MySQL Error 1045, 1142, 1227 / PostgreSQL `permission denied`, `rds_replication`)**: Missing replication or schema privileges -> provides exact `GRANT` SQL statements for MySQL and PostgreSQL and recommends `resume`.
    4. **MySQL Error 1665 (`ER_BINLOG_LOGGING_IMPOSSIBLE`)**: `binlog_format` is `STATEMENT` or `MIXED` instead of `ROW` -> provides `aws rds modify-db-parameter-group` command and recommends `restart`.
    5. **Duplicate Key / Constraint Conflicts (MySQL Error 1062 / PostgreSQL `SQLSTATE 23505`)**: Target conflict during dump or CDC replay -> recommends `restart` for clean target re-initialization.
    6. **PostgreSQL Missing `pglogical` Extension**: `pglogical` missing from `shared_preload_libraries` or database -> provides AWS CLI parameter modification and `CREATE EXTENSION IF NOT EXISTS pglogical;` commands and recommends `resume`.
    7. **Missing Primary Key / `REPLICA IDENTITY` During CDC**: `UPDATE` or `DELETE` fails on tables lacking a Primary Key or Replica Identity -> provides `ALTER TABLE ... ADD PRIMARY KEY` and `ALTER TABLE ... REPLICA IDENTITY FULL` SQL and recommends `resume`.
    8. **Replication Slot / WAL Sender Exhaustion (`max_replication_slots`, `max_wal_senders`)**: Insufficient slots/senders on source RDS PostgreSQL -> provides `pg_replication_slots` inspection SQL and AWS CLI parameter commands.
    9. **Network / Firewall / VPC Peering Timeouts (`Error 2003`, `UNAVAILABLE`, `DEADLINE_EXCEEDED`)**: Blocked connectivity between Cloud SQL / DMS and AWS RDS -> provides Security Group / NACL / VPN troubleshooting steps and recommends `verify`.
    10. **Phase-Aware Fallback**: Contextual guidance tailored to whether the job failed in `FULL_DUMP` vs. `CDC`.

---

### 2. Unified Smart `Check DMS Status` & Self-Healing Controls (`Resume`, `Restart`)
* **Files**:
  * `backend/root_agent/dbmigration/dbmigration_agent.py` (`get_dms_job_structured_status`, `check_dms_status`, `resume_dms_job`, `restart_dms_job`)
  * `backend/main.py` (`/dms/status`)
  * `frontend/main.py` (`/dms/status`, `/dms/resume`, `/dms/restart`)
  * `frontend/templates/index.html`
* **What Changed**:
  * **Unified `Check DMS Status` (`check_dms_status`)**: Consolidated pre-flight verification (`verify`) and Cloud Logging error diagnosis into `check_dms_status` and `get_dms_job_structured_status()` so only a single **Check DMS Status** button is needed in the UI:
    * When the DMS job is `NOT_STARTED`, `check_dms_status` automatically runs `gcloud database-migration migration-jobs verify` to validate network routing, SSL, source parameters, and `pglogical`/binlog readiness before starting the job.
    * When the DMS job is `RUNNING`, `FAILED`, or `STOPPED` (during `FULL_DUMP` or `CDC`), it inspects job metadata and Cloud Logging and automatically returns the structured **AI Error Resolution Advisor** report if any errors exist.
  * **Self-Healing Recovery Actions**:
    * `resume_dms_job`: Runs `gcloud database-migration migration-jobs resume` to continue a paused/failed job from its last CDC checkpoint after source fixes are applied.
    * `restart_dms_job`: Runs `gcloud database-migration migration-jobs restart` when unrecoverable CDC state (such as purged binlogs) requires a fresh `FULL_DUMP`.
  * Updated Step 4 of the UI wizard (`frontend/templates/index.html`) to remove the redundant **Verify DMS Job** and **Diagnose Errors** buttons while keeping **Check DMS Status**, **Resume Job**, **Restart Job**, and the automatic **AI Replication Error Advisor** panel.

---

### 3. Pre-Promotion Safety Gate (Cutover Guardrails)
* **Files**:
  * `backend/root_agent/dbmigration/dbmigration_agent.py` (`promote_target_database`)
* **What Changed**:
  * Enhanced `promote_target_database()` to inspect the current DMS job `state` and `phase` prior to executing `gcloud database-migration migration-jobs promote`.
  * Blocks accidental promotion if the job is in `FAILED` state or still in `FULL_DUMP` (before reaching `CDC`), returning a clear warning unless `force=True` is explicitly passed.

---

### 4. Deep Pre-Migration Readiness & Schema-Level Checks (MySQL & PostgreSQL)
* **Files**:
  * `backend/root_agent/mysql/mysql_agent.py` (`check_mysql_parameters`, `check_mysql_source_schema_readiness`, `build_mysql_remediation_suggestions`)
  * `backend/root_agent/postgres/postgres_agent.py` (`check_postgres_parameters`, `check_postgres_source_schema_readiness`, `build_postgres_remediation_suggestions`)
* **What Changed**:
  * **MySQL**:
    * Added parameter checks for `gtid_mode` and `enforce_gtid_consistency`.
    * Added optional read-only SQL inspection (`check_mysql_source_schema_readiness`) using GCP Secret Manager credentials (`{instance_id}_user` / `{instance_id}_password`) to verify RDS `binlog retention hours` (`CALL mysql.rds_show_configuration;`), detect non-InnoDB tables (`MyISAM`/`MEMORY`), and list user tables missing Primary Keys.
    * Added `build_mysql_remediation_suggestions()` to generate copy-pasteable `aws rds modify-db-parameter-group` and SQL `GRANT` / `rds_set_configuration` commands.
  * **PostgreSQL**:
    * Added optional read-only SQL inspection (`check_postgres_source_schema_readiness`) across all non-system databases to verify whether the `pglogical` extension is installed (`pg_extension`) and identify user tables missing a Primary Key (`REPLICA IDENTITY` risk during CDC).
    * Added `build_postgres_remediation_suggestions()` to output ready-to-run AWS CLI parameter group updates and `CREATE EXTENSION IF NOT EXISTS pglogical;` + `GRANT` SQL templates.

---

### 5. AWS Aurora Cluster Parameter Support & CloudWatch Right-Sizing Telemetry
* **Files**:
  * `backend/root_agent/aws_utils.py` (`get_cluster_parameter_group_settings`, `get_rds_cloudwatch_metrics`)
  * `backend/root_agent/mysql/mysql_agent.py` (`check_mysql_cloudwatch_sizing`)
  * `backend/root_agent/postgres/postgres_agent.py` (`check_postgres_cloudwatch_sizing`)
* **What Changed**:
  * Added `get_cluster_parameter_group_settings()` in `aws_utils.py` so Aurora instances (`aurora-mysql`, `aurora-postgresql`) merge DB cluster parameter group settings (`rds.logical_replication`, `binlog_format`, `shared_preload_libraries`) with instance parameter group settings.
  * Added `get_rds_cloudwatch_metrics()` to query 7-day average and peak `CPUUtilization`, `FreeableMemory`, `ReadIOPS`, and `WriteIOPS` from AWS CloudWatch.
  * Added `check_mysql_cloudwatch_sizing()` and `check_postgres_cloudwatch_sizing()` to include utilization summaries and right-sizing recommendations in the pre-migration report.

---

### 6. Interactive Remediation Commands in HTML Pre-Migration Reports
* **Files**:
  * `backend/root_agent/report_generator.py` (`parse_md_report`, `generate_html_table`, `main`)
* **What Changed**:
  * Updated `parse_md_report()` to extract the `## Suggested Alterations` fenced code block from each instance's Markdown report.
  * Updated `generate_html_table()` to render `WARNING` badges (`class='warn'`) and a collapsible `<details class='remediation-box'>` section displaying copy-pasteable AWS CLI and SQL remediation commands per instance.

---

### 7. Source-vs-Target Data Parity Validation (Row Counts, Deltas, Sequences)
* **Files**:
  * `backend/database_validator.py` (`validate_postgres_instance`, `validate_mysql_instance`, `_merge_source_and_target_metrics`, `validate_instance_databases`)
  * `frontend/templates/index.html`
* **What Changed**:
  * Added safe identifier quoting (`_quote_pg_ident`, `_quote_mysql_ident`) and PostgreSQL sequence count tracking (`information_schema.sequences`).
  * Updated `validate_instance_databases()` to query both Target Cloud SQL and Source AWS RDS (when source credentials and network connectivity are available) and merge metrics via `_merge_source_and_target_metrics()`.
  * Each table now reports `source_rows`, `target_rows`, `diff`, and `status` (`MATCH`, `MISMATCH`, `MISSING_ON_TARGET`, `TARGET_ONLY`, or `VERIFIED`), along with an overall `parity_summary`.
  * Updated the **Database Validation Report** modal section in `frontend/templates/index.html` to display side-by-side `Source Rows`, `Target Rows`, `Delta`, `Status` badges, and `Sequences` counts.

---

### 8. Cloud Run Deployment, Frontend Reverse Proxy & Terraform IAM
* **Files**:
  * `frontend/main.py` (`dms_status_proxy`, `dms_resume_proxy`, `dms_restart_proxy`)
  * `backend/Dockerfile`, `frontend/Dockerfile`
  * `terraform/main.tf` (`google_project_iam_member.backend_logging_viewer`)
* **What Changed**:
  * Added reverse proxy routes in `frontend/main.py` for `/dms/status`, `/dms/resume`, and `/dms/restart` to forward browser requests to `BACKEND_URL`.
  * Updated `backend/Dockerfile` and `frontend/Dockerfile` to install `google-cloud-cli` (replacing deprecated `google-cloud-sdk` Debian apt package).
  * Granted `roles/logging.viewer` to `dms-backend-sa` in `terraform/main.tf` so `fetch_dms_job_logs()` can query Cloud Logging from Cloud Run.
  * Built container images via Google Cloud Build and deployed both services to Cloud Run (`asia-south1` in project `migration-demo-429608`):
    * **Frontend URL**: `https://dms-frontend-214722091571.asia-south1.run.app`
    * **Backend URL**: `https://dms-backend-214722091571.asia-south1.run.app`

---

## Change Log

### 2026-10-01 — Consolidated `Verify DMS Job` & `Diagnose Errors` into `Check DMS Status` (Re-deployed to Cloud Run)
- Merged `verify_dms_job` and `diagnose_dms_job_errors` into `check_dms_status` and `get_dms_job_structured_status(run_verify_if_not_started=True)` in `backend/root_agent/dbmigration/dbmigration_agent.py`, caching `NOT_STARTED` pre-flight verification results in `_LAST_VERIFY_CACHE`.
- Removed redundant **Verify DMS Job** and **Diagnose Errors** buttons from Step 4 in `frontend/templates/index.html`, keeping a single smart **Check DMS Status** button.
- Cleaned up redundant `/dms/verify`, `/dms/diagnose`, `/dms/resume`, and `/dms/restart` proxy routes in `frontend/main.py`.
- Re-built and pushed `gcr.io/migration-demo-429608/dms-backend:latest` (`sha256:69f762d9...`) and `gcr.io/migration-demo-429608/dms-frontend:latest` (`sha256:98292018...`) and rolled out both revisions to Cloud Run via `terraform apply`.

### 2026-10-01 — Cloud Run Deployment (`dms-backend` & `dms-frontend`)
- Added `/dms/verify`, `/dms/diagnose`, `/dms/resume`, and `/dms/restart` proxy routes to `frontend/main.py`.
- Updated `backend/Dockerfile` and `frontend/Dockerfile` to install `google-cloud-cli` instead of `google-cloud-sdk`.
- Added `roles/logging.viewer` IAM binding (`google_project_iam_member.backend_logging_viewer`) for `dms-backend-sa` in `terraform/main.tf`.
- Built and pushed `gcr.io/migration-demo-429608/dms-backend:latest` and `gcr.io/migration-demo-429608/dms-frontend:latest` via Cloud Build.
- Deployed updated `dms-backend` and `dms-frontend` revisions to Cloud Run (`asia-south1`) via `terraform apply`.

### 2026-10-01 — Initial `dms-enhance` Implementation
- Created `dms-enhance` branch from `origin/dms-adk2`.
- Implemented CloudWatch 7-day telemetry and Aurora cluster parameter group discovery in `backend/root_agent/aws_utils.py`.
- Upgraded MySQL and PostgreSQL pre-migration agents (`mysql_agent.py`, `postgres_agent.py`) with GTID checks, optional source schema inspection (binlog retention, non-InnoDB tables, missing PKs, `pglogical` installation), CloudWatch right-sizing advice, and automated AWS CLI/SQL remediation script generation.
- Updated `backend/root_agent/report_generator.py` to parse and render collapsible remediation command blocks and `WARNING` badges in `final_report.html`.
- Added Cloud Logging integration (`fetch_dms_job_logs`), 10-category `FULL_DUMP`/`CDC` error resolution engine (`analyze_dms_error_and_suggest_resolution`), pre-promotion safety gates, and `verify`/`diagnose`/`resume`/`restart` tools in `backend/root_agent/dbmigration/dbmigration_agent.py`.
- Added `/dms/verify`, `/dms/diagnose`, `/dms/resume`, and `/dms/restart` endpoints and structured status responses in `backend/main.py`.
- Upgraded `backend/database_validator.py` to perform side-by-side Source RDS vs. Target Cloud SQL row-count parity and sequence validation.
- Updated `frontend/templates/index.html` with interactive DMS self-healing controls, the AI Error Resolution Advisor card, and side-by-side validation parity tables.
- Created `enhancement.md` to track all enhancements going forward.
