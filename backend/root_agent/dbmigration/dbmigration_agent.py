import subprocess
import os
import json
import logging
import socket
from typing import Dict, Optional
from google.adk.agents import LlmAgent
from dotenv import load_dotenv

load_dotenv()

def get_gcloud_path() -> str:
    import shutil
    path = shutil.which("gcloud")
    if path:
        return path
    home_dir = os.path.expanduser("~")
    common_paths = [
        os.path.join(home_dir, "google-cloud-sdk", "bin", "gcloud"),
        os.path.join(home_dir, "Downloads", "google-cloud-sdk", "bin", "gcloud"),
        "/usr/local/bin/gcloud",
        "/opt/homebrew/bin/gcloud",
        "/usr/bin/gcloud"
    ]
    for p in common_paths:
        if os.path.exists(p):
            return p
    return "gcloud"

def run_cmd(cmd: list[str]) -> tuple[int, str, str]:
    """Runs a shell command and returns exit code, stdout, and stderr."""
    if cmd and cmd[0] == "gcloud":
        cmd[0] = get_gcloud_path()
    logging.info(f"Running command: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr

def get_secret(secret_name: str) -> str:
    """Retrieves secret content from GCP Secret Manager."""
    try:
        from google.cloud import secretmanager
        project_id = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCP_PROJECT_ID")
        if not project_id:
            raise Exception("GCP_PROJECT_ID or GOOGLE_CLOUD_PROJECT environment variable is not set.")
        
        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{project_id}/secrets/{secret_name}/versions/latest"
        response = client.access_secret_version(request={"name": name})
        return response.payload.data.decode("UTF-8").strip()
    except Exception as e:
        logging.warning(f"Failed to retrieve secret '{secret_name}' via SecretManager client: {e}. Falling back to gcloud CLI...")
        
        # Fallback to gcloud CLI
        cmd = ["gcloud", "secrets", "versions", "access", "latest", f"--secret={secret_name}"]
        try:
            ret, out, err = run_cmd(cmd)
            if ret == 0:
                return out.strip()
            else:
                raise Exception(err)
        except FileNotFoundError:
            raise Exception(
                f"gcloud tool was not found and GCP Python client library failed. "
                f"Please ensure that your GCP application credentials are configured correctly. "
                f"Secret Manager client error: {e}"
            )
        except Exception as cli_err:
            raise Exception(
                f"Failed to retrieve secret from GCP Secret Manager (both python client and gcloud failed).\n"
                f"Client error: {e}\n"
                f"gcloud error: {cli_err}"
            )

def get_db_details_from_report(instance_id: str) -> Optional[dict]:
    """Parses local pre-migration markdown reports to find instance details."""
    filenames = ["mysql_report.md", "postgres_report.md"]
    
    backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    for filename in filenames:
        full_path = os.path.join(backend_dir, filename)
        if not os.path.exists(full_path):
            continue
        logging.info(f"Found report file: {full_path}")
        with open(full_path, "r") as f:
            content = f.read()
            
            reports = content.split("# Pre-Migration Report")
            for report in reports:
                # Normalize spaces to find matching instance id
                normalized_report = report.replace(" ", "")
                search_key = f"DBInstanceIdentifier:**{instance_id}"
                if search_key in normalized_report:
                    details = {}
                    for line in report.split("\n"):
                        line = line.strip()
                        if line.startswith("- **Engine:**"):
                            details["engine"] = line.split(":**")[1].strip()
                        elif line.startswith("- **DBInstanceClass:**"):
                            details["instance_class"] = line.split(":**")[1].strip()
                        elif line.startswith("- **Endpoint:**"):
                            endpoint_str = line.split(":**")[1].strip()
                            import ast
                            try:
                                endpoint_val = ast.literal_eval(endpoint_str)
                                details["host"] = endpoint_val.get("Address")
                                details["port"] = endpoint_val.get("Port")
                            except Exception as e:
                                logging.error(f"Failed to parse endpoint dict: {e}")
                        elif line.startswith("- **EngineVersion:**"):
                            details["version"] = line.split(":**")[1].strip()
                        elif line.startswith("- **AllocatedStorage:**"):
                            details["storage"] = line.split(":**")[1].strip()
                    return details
    return None

def map_rds_class_to_cloud_sql_tier(instance_class: str) -> str:
    """Maps AWS RDS instance class to GCP Cloud SQL custom tier."""
    if not instance_class:
        return "db-custom-2-7680" # Default
    
    ic_lower = instance_class.lower()
    parts = ic_lower.split('.')
    if len(parts) < 3:
        return "db-custom-2-7680"
    
    size = parts[2]
    
    if size in ["nano", "micro", "small", "medium"]:
        return "db-custom-2-7680" # 2 vCPU, 7.5 GB RAM (GCP minimum for custom)
    elif size == "large":
        return "db-custom-2-7680" # 2 vCPU, 7.5 GB RAM
    elif size == "xlarge":
        return "db-custom-4-16384" # 4 vCPU, 16 GB RAM
    elif size == "2xlarge":
        return "db-custom-8-32768" # 8 vCPU, 32 GB RAM
    elif size == "4xlarge":
        return "db-custom-16-65536" # 16 vCPU, 64 GB RAM
    elif size == "8xlarge":
        return "db-custom-32-131072" # 32 vCPU, 128 GB RAM
    elif size == "12xlarge":
        return "db-custom-48-196608" # 48 vCPU, 192 GB RAM
    elif size == "16xlarge":
        return "db-custom-64-262144" # 64 vCPU, 256 GB RAM
    elif size == "24xlarge":
        return "db-custom-96-393216" # 96 vCPU, 384 GB RAM
    else:
        return "db-custom-2-7680"

def infer_target_settings(db_details: dict, edition: Optional[str] = None) -> dict:
    """Infers the target Cloud SQL version, tier, and storage size from the source metadata."""
    engine = db_details.get("engine", "mysql").lower()
    version = db_details.get("version", "")
    instance_class = db_details.get("instance_class", "")
    storage = db_details.get("storage")
    
    settings = {}
    
    # Map version
    if engine == "mysql":
        if version.startswith("8."):
            settings["db_version"] = "MYSQL_8_0"
        elif version.startswith("5.7"):
            settings["db_version"] = "MYSQL_5_7"
        else:
            settings["db_version"] = "MYSQL_8_0"
    elif engine in ["postgres", "postgresql"]:
        major = version.split(".")[0]
        if major in ["10", "11", "12", "13", "14", "15", "16", "17"]:
            settings["db_version"] = f"POSTGRES_{major}"
        else:
            settings["db_version"] = "POSTGRES_15"
    else:
        settings["db_version"] = "MYSQL_8_0"

    # Map tier
    tier = map_rds_class_to_cloud_sql_tier(instance_class)
    is_enterprise_plus = False
    if edition and edition.upper().replace("-", "_") == "ENTERPRISE_PLUS":
        is_enterprise_plus = True
    if settings.get("db_version") == "POSTGRES_17":
        is_enterprise_plus = True

    if is_enterprise_plus:
        # Enterprise Plus edition requires db-perf-optimized-N-* tiers
        try:
            parts = tier.split("-")
            # e.g., "db-custom-2-7680" -> ["db", "custom", "2", "7680"]
            if len(parts) >= 3 and parts[1] == "custom":
                vcpus = parts[2]
                tier = f"db-perf-optimized-N-{vcpus}"
            elif not tier.startswith("db-perf-optimized"):
                tier = "db-perf-optimized-N-2"
        except Exception:
            tier = "db-perf-optimized-N-2" # Fallback
    settings["tier"] = tier
    
    # Map storage size (same as source, min 10GB)
    if storage:
        try:
            storage_clean = "".join([c for c in storage if c.isdigit()])
            storage_gb = int(storage_clean)
            settings["storage_size"] = max(10, storage_gb)
        except ValueError:
            settings["storage_size"] = 10
    else:
        settings["storage_size"] = 10
        
    return settings

def get_private_network_for_dms(region: str, preferred_vpc: Optional[str] = None) -> Optional[str]:
    """
    Detects which VPC network has a target VPN gateway in the specified region.
    If preferred_vpc is provided, validates that it exists in the network list first.
    If none is found, falls back to checking 'default'.
    Returns the network name (e.g., 'default') or None if no private network config should be applied.
    """
    # 0. If preferred_vpc is specified, verify it exists and return it
    if preferred_vpc:
        cmd_net = ["gcloud", "compute", "networks", "list", "--format=json"]
        ret_n, out_n, err_n = run_cmd(cmd_net)
        if ret_n == 0:
            try:
                networks = json.loads(out_n)
                network_names = [n.get("name") for n in networks if n.get("name")]
                if preferred_vpc in network_names:
                    logging.info(f"Preferred VPC network '{preferred_vpc}' detected in network list. Using it.")
                    return preferred_vpc
            except Exception as e:
                logging.error(f"Failed to parse networks list JSON: {e}")

    # 1. Check target VPN gateways
    cmd_vpn = ["gcloud", "compute", "target-vpn-gateways", "list", "--format=json"]
    ret, out, err = run_cmd(cmd_vpn)
    if ret == 0:
        try:
            gateways = json.loads(out)
            for gw in gateways:
                gw_region = gw.get("region", "")
                # region is a URL like '.../regions/asia-south1'
                if gw_region.endswith(f"/regions/{region}"):
                    network_url = gw.get("network", "")
                    if network_url:
                        network_name = network_url.split("/")[-1]
                        logging.info(f"Detected target VPN gateway in region '{region}' connected to VPC network: {network_name}")
                        return network_name
        except Exception as e:
            logging.error(f"Failed to parse target-vpn-gateways JSON: {e}")

    # 2. Check fallback: 'default'
    cmd_net = ["gcloud", "compute", "networks", "list", "--format=json"]
    ret_n, out_n, err_n = run_cmd(cmd_net)
    if ret_n == 0:
        try:
            networks = json.loads(out_n)
            network_names = [n.get("name") for n in networks if n.get("name")]
            if "default" in network_names:
                logging.info("Fallback VPC network 'default' detected in network list. Using 'default' as target network.")
                return "default"
        except Exception as e:
            logging.error(f"Failed to parse networks list JSON: {e}")

    logging.warning(f"No VPN gateway found in region '{region}' and no preferred or fallback VPC network is listable. Defaulting to None.")
    return None

def configure_dms_resources(
    migration_job_name: str,
    region: str,
    instance_id: str,
    edition: Optional[str] = None,
    availability_type: Optional[str] = None,
    zone: Optional[str] = None,
    secondary_zone: Optional[str] = None,
    vpc_network: Optional[str] = None,
) -> str:
    """
    Automated DMS configuration: pulls connection metadata from existing pre-migration reports,
    fetches database credentials from GCP Secret Manager, infers optimal target Cloud SQL details,
    and idempotently provisions connection profiles and the DMS job.
    """
    # 1. Fetch details from existing reports
    details = get_db_details_from_report(instance_id)
    if not details:
        return f"Error: Could not find pre-migration report details for database instance '{instance_id}'. Make sure discovery was run first."

    engine = details.get("engine")
    host = details.get("host")
    port = details.get("port")
    
    if not host or not port or not engine:
        return f"Error: Incomplete metadata found in report for instance '{instance_id}': {details}"

    # 2. Fetch credentials from Secret Manager
    try:
        user_secret = f"{instance_id}_user"
        pass_secret = f"{instance_id}_password"
        username = get_secret(user_secret)
        password = get_secret(pass_secret)
    except Exception as e:
        return f"Error fetching credentials for instance '{instance_id}' from GCP Secret Manager: {e}"

    # 3. Infer target settings
    tgt_settings = infer_target_settings(details, edition=edition)
    target_db_version = tgt_settings["db_version"]
    target_tier = tgt_settings["tier"]
    target_storage_size = tgt_settings.get("storage_size")
    target_root_password = password  # Use source password for target root admin for convenience

    database_type = "mysql" if "mysql" in engine.lower() else "postgresql"
    src_profile = f"{migration_job_name}-src"
    tgt_profile = migration_job_name

    # Resolve source hostname to raw IP for direct VPN routing compatibility
    resolved_host = host
    try:
        resolved_host = socket.gethostbyname(host)
        logging.info(f"Resolved source database endpoint '{host}' to private IP: {resolved_host}")
    except Exception as dns_err:
        logging.warning(f"Could not resolve source database endpoint '{host}' to IP. Using original host: {dns_err}")
    
    # 4. Check/Create Source Connection Profile
    check_src_cmd = [
        "gcloud", "database-migration", "connection-profiles", "describe",
        src_profile, f"--region={region}"
    ]
    ret, out, err = run_cmd(check_src_cmd)
    if ret == 0:
        src_msg = f"Source connection profile '{src_profile}' already exists."
    else:
        create_src_cmd = [
            "gcloud", "database-migration", "connection-profiles", "create", database_type,
            src_profile,
            f"--region={region}",
            f"--host={resolved_host}",
            f"--port={str(port)}",
            f"--username={username}",
            f"--password={password}",
            "--role=SOURCE"
        ]
        ret_c, out_c, err_c = run_cmd(create_src_cmd)
        if ret_c != 0:
            return f"Failed to create source connection profile:\nStdout: {out_c}\nStderr: {err_c}"
        src_msg = f"Source connection profile '{src_profile}' created successfully."

    # 5. Check/Create Destination Connection Profile
    check_tgt_cmd = [
        "gcloud", "database-migration", "connection-profiles", "describe",
        tgt_profile, f"--region={region}", "--format=json"
    ]
    ret, out, err = run_cmd(check_tgt_cmd)
    
    profile_exists = (ret == 0)
    if profile_exists:
        profile_state = None
        try:
            profile_data = json.loads(out)
            profile_state = profile_data.get("state")
        except Exception as parse_err:
            logging.error(f"Error parsing connection profile state: {parse_err}")

        if profile_state == "CREATING":
            logging.info(f"Destination connection profile '{tgt_profile}' is still in CREATING state. Skipping SQL instance verification.")
        elif profile_state == "FAILED":
            logging.warning(f"Destination connection profile '{tgt_profile}' is in FAILED state. Deleting and recreating...")
            delete_tgt_cmd = [
                "gcloud", "database-migration", "connection-profiles", "delete",
                tgt_profile, f"--region={region}", "--force", "--quiet"
            ]
            run_cmd(delete_tgt_cmd)
            profile_exists = False
        else:
            # Check if the associated Cloud SQL instance actually exists (for READY or other states)
            project_id = os.getenv("GCP_PROJECT_ID") or os.getenv("PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
            check_sql_cmd = [
                "gcloud", "sql", "instances", "describe",
                tgt_profile, f"--project={project_id}"
            ]
            ret_sql, _, _ = run_cmd(check_sql_cmd)
            if ret_sql != 0:
                logging.warning(
                    f"Destination connection profile '{tgt_profile}' exists with state '{profile_state}', but its associated "
                    f"Cloud SQL instance was not found. Deleting orphaned profile and recreating..."
                )
                delete_tgt_cmd = [
                    "gcloud", "database-migration", "connection-profiles", "delete",
                    tgt_profile, f"--region={region}", "--force", "--quiet"
                ]
                run_cmd(delete_tgt_cmd)
                profile_exists = False

    if profile_exists:
        tgt_msg = f"Destination connection profile '{tgt_profile}' already exists."
    else:
        create_tgt_cmd = [
            "gcloud", "database-migration", "connection-profiles", "create", "cloudsql",
            tgt_profile,
            f"--region={region}",
            f"--source-id={src_profile}",
            f"--database-version-name={target_db_version}",
            f"--tier={target_tier}",
            f"--root-password={target_root_password}",
            "--role=DESTINATION",
            "--auto-storage-increase"
        ]
        if target_storage_size:
            create_tgt_cmd.append(f"--data-disk-size={str(target_storage_size)}")

        if edition:
            gcloud_edition = edition.lower().replace("_", "-")
            create_tgt_cmd.append(f"--edition={gcloud_edition}")

        if availability_type:
            create_tgt_cmd.append(f"--availability-type={availability_type.upper()}")

        if zone:
            create_tgt_cmd.append(f"--zone={zone}")

        if secondary_zone and availability_type == "REGIONAL":
            create_tgt_cmd.append(f"--secondary-zone={secondary_zone}")

        network_to_use = get_private_network_for_dms(region, preferred_vpc=vpc_network)
        if network_to_use:
            create_tgt_cmd.extend([
                f"--private-network={network_to_use}",
                "--no-enable-ip-v4"
            ])

        ret_c, out_c, err_c = run_cmd(create_tgt_cmd)
        if ret_c != 0:
            return f"Failed to initiate destination connection profile creation:\nStdout: {out_c}\nStderr: {err_c}"
        tgt_msg = f"Destination connection profile '{tgt_profile}' creation initiated (Cloud SQL provisioning started)."

    # 6. Check/Create Migration Job
    check_job_cmd = [
        "gcloud", "database-migration", "migration-jobs", "describe",
        migration_job_name, f"--region={region}"
    ]
    ret, out, err = run_cmd(check_job_cmd)
    if ret == 0:
        job_msg = f"Migration job '{migration_job_name}' already exists."
    else:
        create_job_cmd = [
            "gcloud", "database-migration", "migration-jobs", "create",
            migration_job_name,
            f"--region={region}",
            f"--source={src_profile}",
            f"--destination={tgt_profile}",
            "--all-databases",
            "--type=CONTINUOUS"
        ]
        network_to_use = get_private_network_for_dms(region, preferred_vpc=vpc_network)
        if network_to_use:
            create_job_cmd.append(f"--peer-vpc={network_to_use}")
        else:
            create_job_cmd.append("--static-ip")
        ret_c, out_c, err_c = run_cmd(create_job_cmd)
        if ret_c != 0:
            if "FAILED_PRECONDITION" in err_c or "creating" in err_c.lower() or "ready" in err_c.lower() or "active" in err_c.lower():
                job_msg = (
                    f"Note: Connection profiles are configured, but the migration job could not be created yet "
                    f"because the target Cloud SQL instance is still provisioning. Please wait 5-10 minutes and click "
                    f"'Configure DMS Job' again to finalize the job setup."
                )
            else:
                return f"Source and destination connection profiles configured, but failed to create migration job:\nStdout: {out_c}\nStderr: {err_c}"
        else:
            job_msg = f"Migration job '{migration_job_name}' created successfully."

    return f"{src_msg}\n{tgt_msg}\n{job_msg}"

def fetch_dms_job_logs(migration_job_name: str, region: str = "us-central1", limit: int = 10) -> list[str]:
    """
    Queries Google Cloud Logging for recent ERROR or WARNING entries emitted by the DMS migration job
    or its underlying Cloud SQL target replica during FULL_DUMP or CDC replication.
    """
    project_id = os.getenv("GCP_PROJECT_ID") or os.getenv("PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
    log_filter = (
        f'(resource.type="datamigration.googleapis.com/MigrationJob" AND '
        f'resource.labels.migration_job_id="{migration_job_name}") OR '
        f'(resource.type="cloudsql_database" AND textPayload:"{migration_job_name}") '
        f'AND severity>=WARNING'
    )
    cmd = [
        "gcloud", "logging", "read", log_filter,
        f"--limit={limit}", "--format=json"
    ]
    if project_id:
        cmd.append(f"--project={project_id}")

    try:
        ret, out, _ = run_cmd(cmd)
        if ret == 0 and out.strip():
            entries = json.loads(out)
            messages = []
            for entry in entries:
                msg = (
                    entry.get("textPayload")
                    or entry.get("jsonPayload", {}).get("message")
                    or entry.get("protoPayload", {}).get("status", {}).get("message")
                )
                if msg:
                    messages.append(str(msg).strip())
            return messages
    except Exception as e:
        logging.debug(f"Could not fetch Cloud Logging entries for DMS job '{migration_job_name}': {e}")
    return []


def analyze_dms_error_and_suggest_resolution(
    error_code: str,
    error_message: str,
    phase: str = "UNKNOWN",
    log_entries: Optional[list[str]] = None,
) -> dict:
    """
    Analyzes DMS replication errors occurring during FULL_DUMP, CDC, or setup phases,
    and automatically suggests targeted root-cause explanations, SQL/CLI remediation commands,
    and the recommended recovery action (verify, resume, or restart).
    """
    combined_text = f"{error_code} {error_message} {' '.join(log_entries or [])}".lower()
    phase_label = phase if phase and phase != "UNKNOWN" else "FULL_DUMP / CDC"

    # 1. MySQL Error 1236: Purged Binary Logs / Missing GTID during CDC
    if "1236" in combined_text or "purged" in combined_text or "first log file name in binary log index" in combined_text or "gtid_purged" in combined_text:
        return {
            "category": "MySQL CDC Binary Log Purged (Error 1236)",
            "phase": phase_label,
            "root_cause": (
                "During the CDC (Change Data Capture) phase, AWS RDS purged binary log files before DMS "
                "could replicate them. This happens when RDS 'binlog retention hours' is too low or NULL."
            ),
            "resolution_steps": [
                "Connect to the source AWS RDS MySQL instance and increase binary log retention to at least 48–72 hours:",
                "Verify that automated backups are enabled (BackupRetentionPeriod >= 7 days).",
                "Because the purged binlog transactions cannot be recovered incrementally, restart the DMS migration job from a fresh Full Dump."
            ],
            "remediation_commands": (
                "-- Run on Source AWS RDS MySQL:\n"
                "CALL mysql.rds_set_configuration('binlog retention hours', 72);\n"
                "CALL mysql.rds_show_configuration;"
            ),
            "recommended_action": "restart",
        }

    # 2. MySQL Error 1153: Packet too large during FULL_DUMP or CDC
    if "1153" in combined_text or "max_allowed_packet" in combined_text or "packet bigger than" in combined_text:
        return {
            "category": "Packet Size Exceeded (MySQL Error 1153 - max_allowed_packet)",
            "phase": phase_label,
            "root_cause": (
                f"During {phase_label}, a row or binlog event (such as a large BLOB, TEXT, or JSON column) "
                "exceeded the 'max_allowed_packet' limit on the source RDS or target Cloud SQL instance."
            ),
            "resolution_steps": [
                "Increase 'max_allowed_packet' to 512MB (536870912) or 1GB (1073741824) in the AWS RDS Parameter Group.",
                "Ensure the target Cloud SQL instance flag 'max_allowed_packet' is also set to a matching or larger value.",
                "Resume the DMS migration job once the parameter update takes effect."
            ],
            "remediation_commands": (
                "aws rds modify-db-parameter-group \\\n"
                "  --db-parameter-group-name <your-rds-param-group> \\\n"
                "  --parameters \"ParameterName=max_allowed_packet,ParameterValue=536870912,ApplyMethod=immediate\""
            ),
            "recommended_action": "resume",
        }

    # 3. MySQL / Postgres Authentication or Privilege Errors (Error 1045, 1142, 1227, permission denied)
    if (
        "1045" in combined_text
        or "1142" in combined_text
        or "1227" in combined_text
        or "access denied" in combined_text
        or "permission denied" in combined_text
        or "rds_replication" in combined_text
        or "insufficient privilege" in combined_text
    ):
        return {
            "category": "Database Authentication or Insufficient Replication Privileges",
            "phase": phase_label,
            "root_cause": (
                f"During {phase_label}, the migration user lacked required replication or table read privileges, "
                "or the credentials in GCP Secret Manager did not match the source RDS user."
            ),
            "resolution_steps": [
                "Verify that GCP Secret Manager secrets '{instance_id}_user' and '{instance_id}_password' contain valid credentials.",
                "For MySQL: Grant REPLICATION SLAVE, REPLICATION CLIENT, SELECT, RELOAD, and SHOW VIEW privileges.",
                "For PostgreSQL: Grant 'rds_replication', USAGE on all schemas (including 'pglogical'), and SELECT on all tables and sequences.",
                "After applying grants, verify and resume the DMS job."
            ],
            "remediation_commands": (
                "-- For AWS RDS MySQL:\n"
                "GRANT REPLICATION SLAVE, REPLICATION CLIENT, SELECT, RELOAD, SHOW VIEW, TRIGGER ON *.* TO '<migration_user>'@'%';\n"
                "FLUSH PRIVILEGES;\n\n"
                "-- For AWS RDS PostgreSQL (run in each database):\n"
                "GRANT rds_replication TO <migration_user>;\n"
                "GRANT USAGE ON SCHEMA public, pglogical TO <migration_user>;\n"
                "GRANT SELECT ON ALL TABLES IN SCHEMA public, pglogical TO <migration_user>;\n"
                "GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO <migration_user>;"
            ),
            "recommended_action": "resume",
        }

    # 4. PostgreSQL pglogical Extension Missing or Preload Error
    if "pglogical" in combined_text or "shared_preload_libraries" in combined_text or "extension" in combined_text:
        return {
            "category": "PostgreSQL pglogical Extension or Preload Configuration Missing",
            "phase": phase_label,
            "root_cause": (
                f"During {phase_label}, Google Cloud DMS could not initialize logical replication because the "
                "'pglogical' extension is either not preloaded in 'shared_preload_libraries' or 'CREATE EXTENSION pglogical' "
                "was not executed inside every source database."
            ),
            "resolution_steps": [
                "Ensure 'shared_preload_libraries' includes 'pglogical' and 'rds.logical_replication' is '1' in the AWS RDS Parameter Group (requires RDS reboot).",
                "Connect to EVERY non-template database on the source RDS PostgreSQL instance and create the 'pglogical' extension.",
                "Verify and resume/restart the DMS migration job."
            ],
            "remediation_commands": (
                "-- Connect to each database on Source RDS PostgreSQL and run:\n"
                "CREATE EXTENSION IF NOT EXISTS pglogical;\n"
                "GRANT USAGE ON SCHEMA pglogical TO <migration_user>;\n"
                "GRANT SELECT ON ALL TABLES IN SCHEMA pglogical TO <migration_user>;"
            ),
            "recommended_action": "resume",
        }

    # 5. PostgreSQL Missing Primary Key / Replica Identity during CDC UPDATE/DELETE
    if "replica identity" in combined_text or "primary key" in combined_text or "cannot update table" in combined_text or "cannot delete from table" in combined_text:
        return {
            "category": "Table Missing Primary Key / Replica Identity During CDC",
            "phase": "CDC",
            "root_cause": (
                "During CDC replication, an UPDATE or DELETE occurred on a table that does not have a Primary Key "
                "or unique Replica Identity configured."
            ),
            "resolution_steps": [
                "Add a Primary Key to the affected table on the source database (recommended), OR",
                "If a Primary Key cannot be added immediately, set REPLICA IDENTITY FULL on the affected table (use with caution on large tables).",
                "Resume the DMS migration job after updating the table definition."
            ],
            "remediation_commands": (
                "-- Option A (Recommended): Add a Primary Key to the table\n"
                "ALTER TABLE <schema>.<table> ADD PRIMARY KEY (<id_column>);\n\n"
                "-- Option B: Enable Replica Identity Full if no unique key exists\n"
                "ALTER TABLE <schema>.<table> REPLICA IDENTITY FULL;"
            ),
            "recommended_action": "resume",
        }

    # 6. PostgreSQL Replication Slots or WAL Senders Exhausted
    if "replication slot" in combined_text or "max_replication_slots" in combined_text or "max_wal_senders" in combined_text or "max_worker_processes" in combined_text:
        return {
            "category": "PostgreSQL Replication Slots or Worker Processes Exhausted",
            "phase": phase_label,
            "root_cause": (
                f"During {phase_label}, the source PostgreSQL instance ran out of available replication slots, "
                "WAL sender processes, or background worker processes (DMS requires 1 slot/sender per migrated database)."
            ),
            "resolution_steps": [
                "Check active and orphaned replication slots on the source RDS PostgreSQL instance and drop unused slots.",
                "Increase 'max_replication_slots' (>= 15), 'max_wal_senders' (>= 15), and 'max_worker_processes' (>= 16) in the RDS Parameter Group and reboot.",
                "Resume the DMS job after slots are freed."
            ],
            "remediation_commands": (
                "-- Inspect replication slots on Source PostgreSQL:\n"
                "SELECT slot_name, plugin, active FROM pg_replication_slots;\n"
                "-- Drop unused/orphaned slot if inactive:\n"
                "-- SELECT pg_drop_replication_slot('<orphaned_slot_name>');"
            ),
            "recommended_action": "resume",
        }

    # 7. MySQL Binary Log Format Not ROW (Error 1665 / Statement format)
    if "binlog_format" in combined_text or "1665" in combined_text or "statement format" in combined_text:
        return {
            "category": "Incompatible MySQL Binary Log Format (Must be ROW)",
            "phase": phase_label,
            "root_cause": (
                f"During {phase_label}, DMS detected binary log events in STATEMENT or MIXED format. "
                "Google Cloud DMS strictly requires 'binlog_format = ROW'."
            ),
            "resolution_steps": [
                "Update 'binlog_format' to 'ROW' in the AWS RDS DB Parameter Group (immediate apply).",
                "Flush logs on the source RDS instance and resume/restart the DMS migration job."
            ],
            "remediation_commands": (
                "aws rds modify-db-parameter-group \\\n"
                "  --db-parameter-group-name <your-rds-param-group> \\\n"
                "  --parameters \"ParameterName=binlog_format,ParameterValue=ROW,ApplyMethod=immediate\""
            ),
            "recommended_action": "restart",
        }

    # 8. Duplicate Key / Conflicting Writes on Target (MySQL Error 1062 / PG 23505)
    if "1062" in combined_text or "duplicate entry" in combined_text or "duplicate key value" in combined_text or "23505" in combined_text:
        return {
            "category": "Duplicate Key / Target Data Conflict (Error 1062 / SQLSTATE 23505)",
            "phase": phase_label,
            "root_cause": (
                f"During {phase_label}, a duplicate primary/unique key conflict occurred on the target Cloud SQL database. "
                "This typically happens if triggers/events fired on the target or if data was written directly to the replica."
            ),
            "resolution_steps": [
                "Ensure no external applications are writing directly to the target Cloud SQL instance prior to promotion.",
                "Check if any non-deterministic triggers or scheduled events need to be disabled on the target during replication.",
                "If the target schema became out-of-sync during initial dump, restart the DMS job for a clean Full Dump."
            ],
            "remediation_commands": (
                "# Restart the DMS migration job to perform a clean Full Dump + CDC sync:\n"
                f"gcloud database-migration migration-jobs restart <job_name> --region=<region>"
            ),
            "recommended_action": "restart",
        }

    # 9. Network / Connectivity / Firewall / VPN Timeout (Error 2003, 110, UNAVAILABLE, DEADLINE_EXCEEDED)
    if (
        "2003" in combined_text
        or "timed out" in combined_text
        or "timeout" in combined_text
        or "unreachable" in combined_text
        or "connection refused" in combined_text
        or "no route to host" in combined_text
        or "unavailable" in combined_text
        or "deadline_exceeded" in combined_text
    ):
        return {
            "category": "Network Connectivity / Firewall Timeout Between GCP DMS and AWS RDS",
            "phase": phase_label,
            "root_cause": (
                f"During {phase_label}, GCP Database Migration Service could not reach the source AWS RDS endpoint. "
                "Common causes include AWS Security Group rules blocking the GCP VPC/Cloud SQL private IP range, "
                "inactive HA VPN tunnels, or missing VPC peering routes."
            ),
            "resolution_steps": [
                "Verify the AWS RDS Security Group allows inbound TCP traffic on port 3306 (MySQL) or 5432 (PostgreSQL) from your GCP VPC subnet CIDR and DMS peering range.",
                "Verify AWS VPC Route Tables and Network ACLs allow return traffic over the VPN/Interconnect.",
                "Click 'Check DMS Status' to test end-to-end network reachability, then click 'Resume Job'."
            ],
            "remediation_commands": (
                "# Allow GCP VPC CIDR in AWS RDS Security Group:\n"
                "aws ec2 authorize-security-group-ingress \\\n"
                "  --group-id <rds-security-group-id> \\\n"
                "  --protocol tcp --port <3306_or_5432> \\\n"
                "  --cidr <gcp-vpc-cidr-block>"
            ),
            "recommended_action": "verify_and_resume",
        }

    # 10. Generic / Unclassified Phase-Aware Fallback
    return {
        "category": f"DMS Replication Error in {phase_label} Phase ({error_code or 'Unspecified Code'})",
        "phase": phase_label,
        "root_cause": (
            f"The migration job encountered an error during the {phase_label} phase: "
            f"{error_message or 'Refer to GCP Cloud Logging for detailed engine error trace.'}"
        ),
        "resolution_steps": [
            f"Run 'Check DMS Status' to check source-to-target connectivity, credentials, and parameter prerequisites.",
            "If in FULL_DUMP phase: verify source database storage engine (InnoDB for MySQL), max_allowed_packet, and user SELECT/REPLICATION privileges.",
            "If in CDC phase: verify binary log retention (MySQL) or pglogical extension & Primary Keys on all updated tables (PostgreSQL).",
            "Once resolved, use 'Resume Job' (for transient/CDC errors) or 'Restart Job' (for full dump re-initialization)."
        ],
        "remediation_commands": (
            f"# Run pre-flight verification and resume job:\n"
            f"gcloud database-migration migration-jobs verify <job_name> --region=<region>\n"
            f"gcloud database-migration migration-jobs resume <job_name> --region=<region>"
        ),
        "recommended_action": "verify_and_resume",
    }


_LAST_VERIFY_CACHE: Dict[str, dict] = {}


def get_dms_job_structured_status(
    migration_job_name: str,
    region: str = "us-central1",
    run_verify_if_not_started: bool = False,
) -> dict:
    """
    Returns a structured dictionary with DMS job state, phase, replication lag, pre-flight
    verification status (when NOT_STARTED), Cloud Logging error details, and automatic AI error
    resolution advice if any errors exist during PRE_FLIGHT_VERIFY, FULL_DUMP, or CDC.
    """
    cmd = [
        "gcloud", "database-migration", "migration-jobs", "describe",
        migration_job_name, f"--region={region}", "--format=json"
    ]
    ret, out, err = run_cmd(cmd)
    if ret != 0:
        return {
            "configured": False,
            "state": "NONE",
            "phase": "NONE",
            "lag": 0,
            "promoted": False,
            "job_name": migration_job_name,
            "region": region,
            "error_code": None,
            "error_message": None,
            "resolution": None,
        }

    try:
        job_info = json.loads(out)
        state = job_info.get("state", "UNKNOWN")
        phase = job_info.get("phase", "UNKNOWN")
        display_name = job_info.get("displayName", migration_job_name)
        create_time = job_info.get("createTime", "")

        # Extract error object if present
        err_obj = job_info.get("error", {}) or {}
        error_code = str(err_obj.get("code", "")) if err_obj.get("code") is not None else ""
        error_message = err_obj.get("message", "")
        error_details = err_obj.get("details", [])

        verification_passed = None
        verification_details = None
        cache_key = f"{region}:{migration_job_name}"

        # If the job has not started yet and pre-flight verification was requested, run verify
        if run_verify_if_not_started and state == "NOT_STARTED":
            verify_cmd = [
                "gcloud", "database-migration", "migration-jobs", "verify",
                migration_job_name, f"--region={region}"
            ]
            v_ret, v_out, v_err = run_cmd(verify_cmd)
            if v_ret == 0:
                verification_passed = True
                verification_details = (
                    v_out.strip()
                    or "Source and destination connection profiles, network routing, and replication prerequisites verified successfully."
                )
                _LAST_VERIFY_CACHE[cache_key] = {
                    "verification_passed": True,
                    "verification_details": verification_details,
                }
            else:
                verification_passed = False
                error_code = error_code or "VERIFY_FAILED"
                error_message = (v_err.strip() or v_out.strip() or error_message)
                phase = "PRE_FLIGHT_VERIFY"
                _LAST_VERIFY_CACHE[cache_key] = {
                    "verification_passed": False,
                    "error_code": error_code,
                    "error_message": error_message,
                    "phase": phase,
                }
        elif state == "NOT_STARTED" and cache_key in _LAST_VERIFY_CACHE:
            cached = _LAST_VERIFY_CACHE[cache_key]
            verification_passed = cached.get("verification_passed")
            verification_details = cached.get("verification_details")
            if verification_passed is False and not error_message:
                error_code = cached.get("error_code", "VERIFY_FAILED")
                error_message = cached.get("error_message", "")
                phase = cached.get("phase", "PRE_FLIGHT_VERIFY")
        elif state != "NOT_STARTED":
            _LAST_VERIFY_CACHE.pop(cache_key, None)

        # Also check if state is FAILED/STOPPED, verification failed, or if error_message is populated
        has_error = bool(error_message) or state in ["FAILED", "STOPPED"] or (verification_passed is False)
        resolution = None
        recent_logs = []

        if has_error or run_verify_if_not_started:
            recent_logs = fetch_dms_job_logs(migration_job_name, region=region, limit=8)
            if not has_error and recent_logs:
                # Surface Cloud Logging errors even if job describe has not transitioned state yet
                has_error = True
                error_code = error_code or "CLOUD_LOGGING_ERROR"
                error_message = recent_logs[0]

        if has_error:
            details_str = json.dumps(error_details) if error_details else ""
            full_err_msg = f"{error_message} {details_str}".strip()
            resolution = analyze_dms_error_and_suggest_resolution(
                error_code=error_code,
                error_message=full_err_msg,
                phase=phase,
                log_entries=recent_logs,
            )

        return {
            "configured": True,
            "state": state,
            "phase": phase,
            "display_name": display_name,
            "create_time": create_time,
            "lag": 0,
            "promoted": state in ["COMPLETED", "PROMOTED"],
            "job_name": migration_job_name,
            "region": region,
            "verification_passed": verification_passed,
            "verification_details": verification_details,
            "has_error": has_error,
            "error_code": error_code or None,
            "error_message": error_message or (recent_logs[0] if recent_logs else None),
            "recent_logs": recent_logs[:3],
            "resolution": resolution,
        }
    except Exception as e:
        logging.warning(f"Failed to parse DMS structured status: {e}")
        return {
            "configured": False,
            "state": "UNKNOWN",
            "phase": "UNKNOWN",
            "lag": 0,
            "promoted": False,
            "job_name": migration_job_name,
            "region": region,
            "error_code": None,
            "error_message": str(e),
            "resolution": None,
        }


def start_dms_job(migration_job_name: str, region: str = "us-central1") -> str:
    """Starts a DMS migration job using gcloud CLI. Automatically diagnoses startup errors if any occur."""
    cmd = [
        "gcloud", "database-migration", "migration-jobs", "start",
        migration_job_name, f"--region={region}"
    ]
    ret, out, err = run_cmd(cmd)
    if ret == 0:
        return f"Migration job '{migration_job_name}' started successfully."
    else:
        advice = analyze_dms_error_and_suggest_resolution("START_ERROR", err, phase="FULL_DUMP")
        return (
            f"Failed to start migration job '{migration_job_name}':\n"
            f"- **Error**: {err.strip()}\n"
            f"- **Root Cause**: {advice['root_cause']}\n"
            f"- **Suggested Resolution**: {' '.join(advice['resolution_steps'])}\n"
            f"```sql\n{advice['remediation_commands']}\n```"
        )


def resume_dms_job(migration_job_name: str, region: str = "us-central1") -> str:
    """Resumes a paused or failed DMS migration job from where it left off (ideal after fixing CDC or transient Full Dump errors)."""
    cmd = [
        "gcloud", "database-migration", "migration-jobs", "resume",
        migration_job_name, f"--region={region}"
    ]
    ret, out, err = run_cmd(cmd)
    if ret == 0:
        return f"Migration job '{migration_job_name}' in region '{region}' resumed successfully."
    else:
        advice = analyze_dms_error_and_suggest_resolution("RESUME_ERROR", err, phase="CDC")
        return (
            f"Failed to resume migration job '{migration_job_name}':\n"
            f"- **Error**: {err.strip()}\n"
            f"- **Suggested Fix**: {advice['root_cause']} ({' '.join(advice['resolution_steps'])})"
        )


def restart_dms_job(migration_job_name: str, region: str = "us-central1") -> str:
    """Restarts a DMS migration job from a fresh Full Dump (used when binary logs were purged or target data needs re-initialization)."""
    cmd = [
        "gcloud", "database-migration", "migration-jobs", "restart",
        migration_job_name, f"--region={region}"
    ]
    ret, out, err = run_cmd(cmd)
    if ret == 0:
        return f"Migration job '{migration_job_name}' in region '{region}' restarted successfully from the Full Dump phase."
    else:
        return f"Failed to restart migration job '{migration_job_name}':\nStdout: {out}\nStderr: {err}"


def check_dms_status(migration_job_name: str, region: str = "us-central1") -> str:
    """
    Unified DMS status, pre-flight verification, and error diagnostic tool:
    - Checks the live status and phase of the DMS migration job (`describe`).
    - If the job is `NOT_STARTED`, automatically runs pre-flight verification (`verify`) to validate
      network connectivity, SSL, and source/target replication parameters.
    - Inspects Cloud Logging and job error metadata during `FULL_DUMP` or `CDC` and automatically
      provides AI-driven root cause analysis and SQL/CLI resolution steps if any errors are found.
    """
    status = get_dms_job_structured_status(
        migration_job_name,
        region,
        run_verify_if_not_started=True,
    )
    if not status.get("configured"):
        return f"Failed to check migration job status for '{migration_job_name}' in region '{region}': {status.get('error_message', 'Job not found')}"

    status_report = (
        f"### DMS Migration Job Status\n"
        f"- **Job Name**: {status.get('display_name', migration_job_name)}\n"
        f"- **State**: {status.get('state')}\n"
        f"- **Phase**: {status.get('phase')}\n"
        f"- **Created At**: {status.get('create_time', '')}\n"
    )

    if status.get("verification_passed") is True:
        status_report += (
            f"- **Pre-Flight Verification**: PASSED ({status.get('verification_details')})\n"
        )

    if status.get("has_error") and status.get("resolution"):
        res = status["resolution"]
        recent_logs = status.get("recent_logs") or []
        steps_md = "\n".join(f"  {i+1}. {s}" for i, s in enumerate(res.get("resolution_steps", [])))
        logs_md = (
            "\n".join(f"  - `{log}`" for log in recent_logs[:3])
            if recent_logs
            else "  - No additional Cloud Logging entries found."
        )
        status_report += (
            f"- **Error Code**: {status.get('error_code') or 'N/A'}\n"
            f"- **Error Details**: {status.get('error_message') or 'See resolution below'}\n\n"
            f"#### Automatic Error Resolution Advisor ({res.get('category')})\n"
            f"- **Root Cause**: {res.get('root_cause')}\n"
            f"- **Recommended Action**: `{res.get('recommended_action', 'resume').upper()}`\n"
            f"- **Suggested Fix Steps**:\n{steps_md}\n"
            f"- **Remediation Commands**:\n```sql\n{res.get('remediation_commands', '')}\n```\n"
            f"- **Recent Cloud Logging Snippets**:\n{logs_md}\n"
        )
    elif not status.get("has_error"):
        status_report += (
            f"- **Health Diagnosis**: Healthy — no replication errors detected in DMS metadata or Cloud Logging.\n"
        )

    return status_report


def promote_target_database(migration_job_name: str, region: str = "us-central1") -> str:
    """
    Checks pre-promotion readiness and promotes the target database of a DMS migration job using gcloud CLI.
    """
    status = get_dms_job_structured_status(migration_job_name, region)
    state = status.get("state", "UNKNOWN")
    phase = status.get("phase", "UNKNOWN")

    if status.get("has_error"):
        res = status.get("resolution") or {}
        return (
            f"Pre-Promotion Safety Gate Blocked Promotion: Migration job '{migration_job_name}' currently has an active error "
            f"(State: {state}, Phase: {phase}).\n"
            f"- **Error**: {status.get('error_message')}\n"
            f"- **Suggested Resolution**: {res.get('root_cause', 'Resolve replication errors before promoting.')}"
        )

    cmd = [
        "gcloud", "database-migration", "migration-jobs", "promote",
        migration_job_name, f"--region={region}"
    ]
    ret, out, err = run_cmd(cmd)
    if ret == 0:
        return (
            f"Target database for migration job '{migration_job_name}' promoted successfully. Migration complete!\n\n"
            f"**Post-Promotion Cutover Checklist:**\n"
            f"- Target Cloud SQL instance is now a standalone primary instance accepting read/write traffic.\n"
            f"- For PostgreSQL: verify sequence values (`SELECT setval(...)`) if sequences were heavily incremented right before cutover.\n"
            f"- Update application connection strings / Cloud SQL Auth Proxy to point to the promoted Cloud SQL endpoint."
        )
    else:
        return f"Failed to promote database:\nStdout: {out}\nStderr: {err}"


# --- Agent Definition ---
dbmigration_dms_agent = LlmAgent(
    name="DBMigrationDMSAgent",
    model=os.getenv("MODEL"),
    instruction="""You are an expert on Google Cloud Database Migration Service (DMS).
Your task is to help the user configure, start, check status/verify/diagnose errors for, resume/restart, and promote database migration jobs.

You have tools to:
- Configure DMS resources (`configure_dms_resources`: creates source connection profile, target connection profile, and migration job).
- Start a DMS migration job (`start_dms_job`).
- Check the status of a DMS migration job (`check_dms_status`: automatically runs pre-flight verification if `NOT_STARTED`, checks live replication status and Cloud Logging, and provides AI error resolution suggestions if the job encountered errors during Full Dump or CDC).
- Resume a paused or failed DMS migration job (`resume_dms_job`).
- Restart a DMS migration job from Full Dump (`restart_dms_job`).
- Promote the target database (`promote_target_database`: completes the migration job with pre-promotion safety checks).

Choose the appropriate tool based on the user's intent:
- If the user wants to configure or setup DMS, extract:
  - migration_job_name
  - region (default to 'us-central1' if not specified)
  - instance_id (the AWS database instance identifier, e.g., gemini-mysql-instance-1)
  - edition (e.g. 'ENTERPRISE' or 'ENTERPRISE_PLUS')
  - availability_type (e.g. 'ZONAL' or 'REGIONAL')
  - zone (e.g. primary zone)
  - secondary_zone (e.g. secondary zone for HA)
  - vpc_network (e.g. custom VPC network selected by user)
  And call `configure_dms_resources`.
- If the user wants to start the migration job, call `start_dms_job`.
- If the user wants to check the status, verify pre-flight readiness, or diagnose/troubleshoot errors of the migration job, call `check_dms_status`.
- If the user wants to resume a paused or fixed migration job, call `resume_dms_job`.
- If the user wants to restart a migration job from scratch / Full Dump, call `restart_dms_job`.
- If the user wants to promote the database or complete migration, call `promote_target_database`.

Whenever an error is detected during Pre-Flight Verification, Full Dump, or CDC, always highlight the error code, root cause, exact remediation commands (SQL / AWS CLI / gcloud), and whether the user should resume or restart the job.
Provide a clear, human-readable summary of the tool output as your final response.
""",
    description="Handles all requests for configuring DMS connection profiles, starting/resuming/restarting migration jobs, checking status (including pre-flight verification and Full Dump/CDC error diagnosis), and promoting target databases.",
    tools=[
        configure_dms_resources,
        start_dms_job,
        check_dms_status,
        resume_dms_job,
        restart_dms_job,
        promote_target_database,
    ],
)
