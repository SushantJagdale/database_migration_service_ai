# 🤖 Project Plan: AWS RDS Pre-Migration Data Collector Agents (Multi-Agent Orchestration)

## 1. Project Overview

This plan outlines the creation of a **Root Orchestration Agent** which will route user queries to two specialized child agents: **MySQL DMS Agent** and **PostgreSQL DMS Agent**. This multi-agent structure performs a deep analysis of AWS RDS instances and their associated **DB Parameter Groups** to ensure all configuration data meets the strict prerequisites for a **Google Cloud Database Migration Service (DMS)** continuous migration job.

The agents will be built using the **Google ADK** (`from google.adk import Agent`) and use the local AWS CLI **default profile** for credentials.

---

## 2. Tech Stack

### Agent Development Environment

- **Language:** Python 3.x
- **Agent/Orchestration:** **Google ADK Agent (Agent Framework)**
    * **Components:** `root_orchestrator.py`, `mysql_agent.py`, `postgres_agent.py`
- **AWS Interface:** **Boto3** (AWS SDK for Python)
- **DB Connectors:** Use **Boto3 RDS API** to search all RDS databases (MySQL, PostgreSQL, etc.) in the account and list their instance IDs, engine types, and parameter groups in an internal list for processing. The list of database IDs should also be exported to a temporary file named `db_list.txt`.
- **Goal:** Automate prerequisite checks for GCP DMS via intelligent query routing.

### Target Environment

- **Source:** AWS RDS MySQL and AWS RDS PostgreSQL
- **Connectivity:** Secure access via local machine's AWS CLI default profile.

---

## 3. Core Functionalities and Data Requirements (DMS Compliance)

The agents will collect and validate the following DMS-critical parameters using AWS Boto3 API calls to check Parameter Group settings.

| Category | AWS RDS MySQL Collector | AWS RDS PostgreSQL Collector |
| :--- | :--- | :--- |
| **Version Check** | MySQL Version (must be 5.7+ or 8.0+) | PostgreSQL Version (must be 10+, 11+, 12+, 13+, 14+, or 15+) |
| **Replication Format** | **Binary Logging:** Status (`log_bin: ON`), Format (`binlog_format: ROW`) | **Logical Replication:** Status (`wal_level: logical`), Required Extensions (`pglogical` or built-in slots) |
| **User Privileges** | `REPLICATION SLAVE`, `REPLICATION CLIENT`, `SELECT` on all tables, etc. | `rds_superuser` or equivalent role to set up replication slots/publication. |
| **DB Parameter Group** | **Validation & Suggestion:** Validate `binlog_format` and `log_bin` settings in the group. **Suggest alteration if needed.** | **Validation & Suggestion:** Validate `wal_level` and `max_replication_slots` in the group. **Suggest alteration if needed.** |

---

## 4. Agent and Tooling Components

### Shared Utility (`aws_utils.py`) - Enhanced

- **`load_aws_credentials()`:** Loads credentials from the default profile using Boto3.
- **`list_all_rds_dbs()`:** Uses Boto3 `describe_db_instances` to list all RDS databases in the account and output the list to **`db_list.txt`**.
- **`get_rds_metadata(instance_id)`:** Uses Boto3 `describe_db_instances` to fetch configuration data (Region, AZ, Endpoint, Parameter Group Name).
- **`get_parameter_group_settings(group_name, engine_type)`:** Uses Boto3 `describe_db_parameters` to fetch the current values of parameters in the attached group.

### Agent 1: MySQL Collector (`mysql_agent.py`) - Child Agent

- **Tools:** **`check_mysql_replication_params`**, **`check_mysql_version`**, **`suggest_mysql_alteration`**. (All Boto3 function calls defined in `aws_utils.py`)

### Agent 2: PostgreSQL Collector (`postgres_agent.py`) - Child Agent

- **Tools:** **`check_postgres_logical_params`**, **`check_postgres_version`**, **`suggest_postgres_alteration`**. (All Boto3 function calls defined in `aws_utils.py`)

### Agent 3: Root Orchestrator (`root_orchestrator.py`) - Parent Agent

- **Role:** Accepts user prompt, determines database engine, and delegates to the appropriate child agent.

---

## 5. Implementation Task List - checkmark as and when the task is implemented.

### Phase 1: Setup and Boto3 Connector

- [ ] Initialize Python project and install core dependencies (`boto3`, Google SDK, connectors).
- [ ] Create **`aws_utils.py`** and test credential loading using the `default` profile.
- [ ] Implement `get_rds_metadata(instance_id)`, `list_all_rds_dbs()`, and `get_parameter_group_settings()` in `aws_utils.py`.
- [ ] Create placeholder agent files: `mysql_agent.py`, `postgres_agent.py`, and **`root_orchestrator.py`**.

### Phase 2: Child Agent Development (MySQL & PostgreSQL)

- [ ] **[MySQL]** Implement the `check_mysql_version`, `check_mysql_replication_params`, and `suggest_mysql_alteration` functions.
- [ ] **[MySQL]** Define the **Google ADK Agent** (`mysql_dms_agent`) in `mysql_agent.py`. Agent must be created using `from google.adk import Agent` class.
- [ ] **[MySQL]** Register the MySQL tools for the agent and finalize its workflow.
- [ ] **[PostgreSQL]** Implement the `check_postgres_version`, `check_postgres_logical_params`, and `suggest_postgres_alteration` functions.
- [ ] **[PostgreSQL]** Define the **Google ADK Agent** (`postgres_dms_agent`) in `postgres_agent.py`. Agent must be created using `from google.adk import Agent` class.
- [ ] **[PostgreSQL]** Register the PostgreSQL tools for the agent and finalize its workflow.

### Phase 3: Root Agent Orchestration

- [ ] **Define the Root Agent:** Initialize the **Google ADK Agent** (`root_orchestrator`) in `root_orchestrator.py` using `from google.adk import Agent` class.
- [ ] **Equip Root Agent with Child Agents:** Configure the Root Agent to recognize and have access to call the `mysql_dms_agent` and `postgres_dms_agent`.
- [ ] **Routing Logic:** Configure the Root Agent's prompt and workflow to analyze the user's input for keywords (e.g., "MySQL," "binlog," "Postgres," "wal_level") and delegate the execution to the appropriate child agent.
- [ ] **Execution:** Define the final entry point script to take the user prompt and pass it to the `root_orchestrator` instance.

### Phase 4: Finalization, Reporting, and Testing

- [ ] Refine **`report_generator.py`** to handle results from the orchestrated calls and clearly display **PASS/FAIL** status and the **SUGGESTED ALTERATION**.
- [ ] Add exception handling for common errors (e.g., routing failure, child agent execution error).
- [ ] Document the required **local AWS CLI default profile setup** and the usage instructions for the Root Agent.
- [ ] Final end-to-end testing against live (non-production) AWS RDS MySQL and PostgreSQL instances, validating the routing capability with diverse user prompts.