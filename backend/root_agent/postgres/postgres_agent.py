from ..aws_utils import get_rds_metadata, get_parameter_group_settings, list_all_rds_dbs, get_specific_db_parameter
from google.adk.agents import LlmAgent
from ..report_generator import generate_report
import os
import asyncio
from typing import Optional
import subprocess
from dotenv import load_dotenv

load_dotenv()

# --- Tool Functions for a SINGLE PostgreSQL Instance ---
def check_postgres_version(instance_id: str, region: str) -> str:
    """Checks the PostgreSQL version of an RDS instance."""
    try:
        metadata = get_rds_metadata(instance_id, region)
        if metadata:
            engine_version = metadata.get('EngineVersion', 'Unknown')
            supported_versions = ['10', '11', '12', '13', '14', '15', '16', '17']
            if any(engine_version.startswith(v) for v in supported_versions):
                return "PASS: Compatible."
            else:
                return f"FAIL: Not compatible. Must be one of {supported_versions}."
        return "FAIL: Could not retrieve RDS metadata."
    except Exception as e:
        return f"Error checking PostgreSQL version: {e}"

def check_postgres_logical_params(instance_id: str, region: str) -> str:
    """Checks PostgreSQL logical replication parameters (wal_level, max_replication_slots, rds.logical_replication, shared_preload_libraries)."""
    try:
        metadata = get_rds_metadata(instance_id, region)
        if not metadata or not metadata.get('DBParameterGroups'):
            return "FAIL: Could not retrieve parameter group for the instance."
        group_name = metadata['DBParameterGroups'][0]['DBParameterGroupName']
        params = get_parameter_group_settings(group_name, region)
        if not params:
            return f"FAIL: Could not retrieve parameters for group {group_name}."
        
        wal_level = next((p.get('ParameterValue') for p in params if p['ParameterName'] == 'wal_level'), 'Not Set')
        max_slots = next((p.get('ParameterValue') for p in params if p['ParameterName'] == 'max_replication_slots'), 'Not Set')
        rds_logical = next((p.get('ParameterValue') for p in params if p['ParameterName'] == 'rds.logical_replication'), 'Not Set')
        shared_preload = next((p.get('ParameterValue') for p in params if p['ParameterName'] == 'shared_preload_libraries'), 'Not Set')

        results = []
        if rds_logical == '1':
            results.append("PASS: rds.logical_replication is 1.")
        else:
            results.append(f"FAIL: rds.logical_replication is '{rds_logical}'. It must be set to '1' (ON).\nSuggestion: Set rds.logical_replication to 1 in the Parameter Group and reboot the database instance.")

        if wal_level == 'logical':
            results.append("PASS: wal_level is logical.")
        else:
            results.append(f"FAIL: wal_level is '{wal_level}'. It must be 'logical'.\nSuggestion: Ensure rds.logical_replication is set to 1 and the database instance has been rebooted to apply the change.")
        
        if max_slots != 'Not Set' and int(max_slots) > 5:
            results.append(f"PASS: max_replication_slots is set to {max_slots}.")
        else:
            results.append(f"FAIL: max_replication_slots is '{max_slots}'. It should be greater than 5.\nSuggestion: Set max_replication_slots to a value greater than 5 (e.g. 10) in the Parameter Group.")
            
        if shared_preload != 'Not Set' and 'pglogical' in shared_preload:
            results.append(f"PASS: pglogical is loaded in shared_preload_libraries ({shared_preload}).")
        else:
            results.append(f"FAIL: pglogical is missing from shared_preload_libraries. Current: '{shared_preload}'.\nSuggestion: Add 'pglogical' to shared_preload_libraries in the Parameter Group and reboot the instance. Also, ensure you run 'CREATE EXTENSION pglogical;' in each database to be migrated.")
            
        return "\n".join(results)
    except Exception as e:
        return f"Error checking PostgreSQL logical params: {e}"

def check_postgres_worker_params(instance_id: str, region: str) -> str:
    """Checks PostgreSQL worker and lock parameters."""
    try:
        metadata = get_rds_metadata(instance_id, region)
        if not metadata or not metadata.get('DBParameterGroups'):
            return "FAIL: Could not retrieve parameter group for the instance."
        group_name = metadata['DBParameterGroups'][0]['DBParameterGroupName']
        
        max_wal_senders_param = get_specific_db_parameter(group_name, region, 'max_wal_senders')
        max_workers_param = get_specific_db_parameter(group_name, region, 'max_worker_processes')
        max_locks_param = get_specific_db_parameter(group_name, region, 'max_locks_per_transaction')

        results = []
        # Safely get parameter values
        max_wal_senders = int(max_wal_senders_param.get('ParameterValue', 0)) if max_wal_senders_param else 0
        max_workers = int(max_workers_param.get('ParameterValue', 0)) if max_workers_param else 0
        max_locks = int(max_locks_param.get('ParameterValue', 0)) if max_locks_param else 0

        # Check max_wal_senders
        if max_wal_senders >= 10:
            results.append(f"PASS: max_wal_senders is set to a reasonable value ({max_wal_senders}).")
        else:
            results.append(f"FAIL: max_wal_senders is '{max_wal_senders}'. It should be >= 10.")

        # Check max_worker_processes
        if max_workers >= 8:
            results.append(f"PASS: max_worker_processes is set to a reasonable value ({max_workers}).")
        else:
            results.append(f"FAIL: max_worker_processes is '{max_workers}'. It should be >= 8.")

        # Check max_locks_per_transaction
        if max_locks >= 64:
            results.append(f"PASS: max_locks_per_transaction is set to a reasonable value ({max_locks}).")
        else:
            results.append(f"FAIL: max_locks_per_transaction is '{max_locks}'. It should be >= 64.")
            
        return "\n".join(results)
    except Exception as e:
        return f"Error checking PostgreSQL worker params: {e}"

def generate_single_postgres_report(instance_id: str, region: str) -> str:
    """Generates a pre-migration report for a single PostgreSQL RDS instance."""
    rds_metadata = get_rds_metadata(instance_id, region)
    # Add the region to the metadata for the report
    if rds_metadata:
        rds_metadata['Region'] = region
        
    validation_results = {
        "Version Check": check_postgres_version(instance_id, region),
        "Logical Replication": check_postgres_logical_params(instance_id, region),
        "Worker Processes & Locks": check_postgres_worker_params(instance_id, region),
    }
    return generate_report("PostgreSQL", rds_metadata, validation_results, "")

# --- Multi-Instance Orchestration ---
async def discover_and_generate_postgres_reports(user_prompt: str, region_name: Optional[str] = None) -> str:
    """
    Discovers all PostgreSQL RDS instances, performs DMS checks, and generates a consolidated report.
    
    Args:
        user_prompt: The user's original query.
        region_name: Optional AWS region name (e.g. 'us-east-1', 'ap-south-1') to filter instances.
    """
    def sync_run():
        try:
            if region_name:
                print(f"PostgreSQL Agent: Discovering RDS instances in region {region_name}...")
                all_dbs = list_all_rds_dbs(region_name=region_name)
            else:
                print("PostgreSQL Agent: Discovering all RDS instances across all regions...")
                all_dbs = list_all_rds_dbs()
            postgres_dbs = [db for db in all_dbs if 'postgres' in db.get('Engine', '').lower()]

            backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            report_path = os.path.join(backend_dir, "postgres_report.md")

            if not postgres_dbs:
                with open(report_path, "w") as f:
                    f.write("")
                return "No PostgreSQL RDS instances were found."

            print(f"PostgreSQL Agent: Found {len(postgres_dbs)} PostgreSQL instance(s). Generating reports...")
            
            final_report_content = ""
            
            for db in postgres_dbs:
                instance_id = db.get('DBInstanceIdentifier')
                region = db.get('Region')
                if not instance_id or not region:
                    continue
                
                print(f"PostgreSQL Agent: Processing instance {instance_id} in {region}...")
                report_part = generate_single_postgres_report(instance_id, region)
                final_report_content += report_part

            with open(report_path, "w") as f:
                f.write(final_report_content)
            
            return f"Consolidated report for {len(postgres_dbs)} PostgreSQL instance(s) generated and saved to {report_path}."
        except Exception as e:
            print(f"ERROR in PostgreSQL Agent: {e}")
            import traceback
            traceback.print_exc()
            return f"An error occurred in the PostgreSQL agent: {e}"

    return await asyncio.to_thread(sync_run)

# --- Agent Definition ---
postgres_dms_agent = LlmAgent(
    name="PostgreSQLDMSCheckerAgent",
    model=os.getenv("MODEL"),
    instruction="""You are an expert on AWS RDS for PostgreSQL and Google Cloud DMS.
    Your task is to fulfill a user's request to check their RDS instances for DMS compatibility.
    
    CRITICAL: Check if the user's prompt specifies checking database engines. If the user explicitly asks for only MySQL or excludes PostgreSQL, do NOT call the `discover_and_generate_postgres_reports` tool. Just respond saying that PostgreSQL checks are skipped.
    Otherwise, call the `discover_and_generate_postgres_reports` tool, passing the user's original prompt.
    
    Determine the regional scope from the user's prompt and pass it as `region_name`:
    - If they specify a single region or city (e.g., "mumbai", "ap-south-1", "mumbai region"), resolve it to its official AWS region code (e.g., "ap-south-1").
    - If they specify a broader regional scope (e.g., "US region", "databases in US", "US regions"), resolve it to a wildcard pattern (e.g., "us-*").
    - If they specify Europe (e.g., "Europe region"), resolve it to "eu-*".
    - If they specify Asia, resolve it to "ap-*".
    - Otherwise (if no regional scope is specified), pass None.
    
    Your final output must be the full, consolidated report generated by the tool, or the skip message.
    You are an agent. Your internal name is `PostgreSQLDMSCheckerAgent`. The description about you is: Handles all requests for checking AWS RDS for PostgreSQL instances. It automatically discovers all PostgreSQL instances and generates a consolidated DMS pre-requisite report.
    """,
    description="Handles all requests for checking AWS RDS for PostgreSQL instances. It automatically discovers all PostgreSQL instances and generates a consolidated DMS pre-requisite report.",
    tools=[
        discover_and_generate_postgres_reports,
    ],
)