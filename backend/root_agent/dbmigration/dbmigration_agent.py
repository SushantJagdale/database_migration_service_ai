import subprocess
import os
import json
import logging
import socket
from typing import Optional
from google.adk.agents import LlmAgent
from dotenv import load_dotenv

load_dotenv()

def run_cmd(cmd: list[str]) -> tuple[int, str, str]:
    """Runs a shell command and returns exit code, stdout, and stderr."""
    logging.info(f"Running command: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr

def get_secret(secret_name: str) -> str:
    """Retrieves secret content from GCP Secret Manager."""
    cmd = ["gcloud", "secrets", "versions", "access", "latest", f"--secret={secret_name}"]
    ret, out, err = run_cmd(cmd)
    if ret == 0:
        return out.strip()
    else:
        raise Exception(f"Failed to retrieve secret '{secret_name}' from GCP Secret Manager: {err}")

def get_db_details_from_report(instance_id: str) -> Optional[dict]:
    """Parses local pre-migration markdown reports to find instance details."""
    filenames = ["mysql_report.md", "postgres_report.md"]
    
    # Check multiple candidate directories for the report files
    search_dirs = [
        os.getcwd(),
        os.path.join(os.getcwd(), "backend") if not os.getcwd().endswith("backend") else None,
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ]
    search_dirs = [d for d in search_dirs if d and os.path.exists(d)]

    for filename in filenames:
        for s_dir in search_dirs:
            full_path = os.path.join(s_dir, filename)
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

def infer_target_settings(db_details: dict) -> dict:
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
    if settings.get("db_version") == "POSTGRES_17":
        # Enterprise Plus edition is required for PostgreSQL 17, which needs db-perf-optimized-N-* tiers
        try:
            parts = tier.split("-")
            # e.g., "db-custom-2-7680" -> ["db", "custom", "2", "7680"]
            if len(parts) >= 3 and parts[1] == "custom":
                vcpus = parts[2]
                tier = f"db-perf-optimized-N-{vcpus}"
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

def get_private_network_for_dms(region: str) -> Optional[str]:
    """
    Detects which VPC network has a target VPN gateway in the specified region.
    If none is found, checks if 'gc-vpc' network exists.
    Returns the network name (e.g., 'gc-vpc' or 'default') or None if no private network config should be applied.
    """
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

    # 2. If no VPN gateway matches, check if 'gc-vpc' network exists
    cmd_net = ["gcloud", "compute", "networks", "list", "--format=json"]
    ret_n, out_n, err_n = run_cmd(cmd_net)
    if ret_n == 0:
        try:
            networks = json.loads(out_n)
            network_names = [n.get("name") for n in networks if n.get("name")]
            if "gc-vpc" in network_names:
                logging.info("VPC network 'gc-vpc' detected in network list. Using 'gc-vpc' as target network.")
                return "gc-vpc"
        except Exception as e:
            logging.error(f"Failed to parse networks list JSON: {e}")

    logging.warning(f"No VPN gateway found in region '{region}' and VPC network 'gc-vpc' is not listable. Defaulting to None.")
    return None

def configure_dms_resources(
    migration_job_name: str,
    region: str,
    instance_id: str
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
    tgt_settings = infer_target_settings(details)
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
        tgt_profile, f"--region={region}"
    ]
    ret, out, err = run_cmd(check_tgt_cmd)
    if ret == 0:
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
            "--role=DESTINATION"
        ]
        if target_storage_size:
            create_tgt_cmd.append(f"--data-disk-size={str(target_storage_size)}")

        private_network = get_private_network_for_dms(region)
        if private_network:
            create_tgt_cmd.extend([
                f"--private-network={private_network}",
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
        private_network = get_private_network_for_dms(region)
        if private_network:
            create_job_cmd.append(f"--peer-vpc={private_network}")
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

def start_dms_job(migration_job_name: str, region: str = "us-central1") -> str:
    """Starts a DMS migration job using gcloud CLI."""
    cmd = [
        "gcloud", "database-migration", "migration-jobs", "start",
        migration_job_name, f"--region={region}"
    ]
    ret, out, err = run_cmd(cmd)
    if ret == 0:
        return f"Migration job '{migration_job_name}' started successfully."
    else:
        return f"Failed to start migration job:\nStdout: {out}\nStderr: {err}"

def check_dms_status(migration_job_name: str, region: str = "us-central1") -> str:
    """Checks the status of a DMS migration job using gcloud CLI."""
    cmd = [
        "gcloud", "database-migration", "migration-jobs", "describe",
        migration_job_name, f"--region={region}", "--format=json"
    ]
    ret, out, err = run_cmd(cmd)
    if ret == 0:
        try:
            job_info = json.loads(out)
            state = job_info.get("state", "UNKNOWN")
            phase = job_info.get("phase", "UNKNOWN")
            display_name = job_info.get("displayName", migration_job_name)
            create_time = job_info.get("createTime", "")
            
            status_report = (
                f"### DMS Migration Job Status\n"
                f"- **Job Name**: {display_name}\n"
                f"- **State**: {state}\n"
                f"- **Phase**: {phase}\n"
                f"- **Created At**: {create_time}\n"
            )
            
            if "error" in job_info:
                status_report += f"- **Error Details**: {job_info['error'].get('message', 'No message')}\n"
                
            return status_report
        except Exception as e:
            return f"Failed to parse job status JSON:\n{out}\nError: {e}"
    else:
        return f"Failed to check migration job status:\nStdout: {out}\nStderr: {err}"

def promote_target_database(migration_job_name: str, region: str = "us-central1") -> str:
    """Promotes the target database of a DMS migration job using gcloud CLI."""
    cmd = [
        "gcloud", "database-migration", "migration-jobs", "promote",
        migration_job_name, f"--region={region}"
    ]
    ret, out, err = run_cmd(cmd)
    if ret == 0:
        return f"Target database for migration job '{migration_job_name}' promoted successfully. Migration complete!"
    else:
        return f"Failed to promote database:\nStdout: {out}\nStderr: {err}"

# --- Agent Definition ---
dbmigration_dms_agent = LlmAgent(
    name="DBMigrationDMSAgent",
    model=os.getenv("MODEL"),
    instruction="""You are an expert on Google Cloud Database Migration Service (DMS).
Your task is to help the user configure, start, check status of, and promote database migration jobs.

You have tools to:
- Configure DMS resources (creates source connection profile, target connection profile, and migration job).
- Start a DMS migration job.
- Check the status of a DMS migration job.
- Promote the target database (completes the migration job).

Choose the appropriate tool based on the user's intent:
- If the user wants to configure or setup DMS, extract:
  - migration_job_name
  - region (default to 'us-central1' if not specified)
  - instance_id (the AWS database instance identifier, e.g., gemini-mysql-instance-1)
  And call `configure_dms_resources`.
- If the user wants to start the migration job, extract:
  - migration_job_name
  - region
  And call `start_dms_job`.
- If the user wants to check the status or get info of the migration job, extract:
  - migration_job_name
  - region
  And call `check_dms_status`.
- If the user wants to promote the database or complete migration, extract:
  - migration_job_name
  - region
  And call `promote_target_database`.
  
Provide a clear, human-readable summary of the tool output as your final response.
""",
    description="Handles all requests for configuring DMS connection profiles, creating/starting migration jobs, checking status, and promoting target databases.",
    tools=[
        configure_dms_resources,
        start_dms_job,
        check_dms_status,
        promote_target_database,
    ],
)
