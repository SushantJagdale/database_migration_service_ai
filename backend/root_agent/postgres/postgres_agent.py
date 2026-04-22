from ..aws_utils import get_rds_metadata, get_parameter_group_settings, list_all_rds_dbs, get_specific_db_parameter
from google.adk.agents import LlmAgent
from ..html_report_generator import generate_report
import os
import subprocess
#from dotenv import load_dotenv
#from ..config import llm

#load_dotenv()

# --- Tool Functions for a SINGLE PostgreSQL Instance ---
def check_postgres_version(instance_id: str, region: str) -> str:
    """Checks the PostgreSQL version of an RDS instance."""
    try:
        metadata = get_rds_metadata(instance_id, region)
        if metadata:
            engine_version = metadata.get('EngineVersion', 'Unknown')
            supported_versions = ['10', '11', '12', '13', '14', '15']
            if any(engine_version.startswith(v) for v in supported_versions):
                return "PASS: Compatible."
            else:
                return f"FAIL: Not compatible. Must be one of {supported_versions}."
        return "FAIL: Could not retrieve RDS metadata."
    except Exception as e:
        return f"Error checking PostgreSQL version: {e}"

def check_postgres_logical_params(instance_id: str, region: str) -> str:
    """Checks PostgreSQL logical replication parameters (wal_level, max_replication_slots)."""
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

        results = []
        if wal_level == 'logical':
            results.append("PASS: wal_level is logical.")
        else:
            results.append(f"FAIL: wal_level is '{wal_level}'. It must be 'logical'.")
        
        if max_slots != 'Not Set' and int(max_slots) > 5:
            results.append(f"PASS: max_replication_slots is set to {max_slots}.")
        else:
            results.append(f"FAIL: max_replication_slots is '{max_slots}'. It should be greater than 5.")
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
def discover_and_generate_postgres_reports(user_prompt: str) -> str:
    """
    Discovers all PostgreSQL RDS instances, performs DMS checks, and generates a consolidated report.
    """
    try:
        print("PostgreSQL Agent: Discovering all RDS instances...")
        all_dbs = list_all_rds_dbs()
        postgres_dbs = [db for db in all_dbs if 'postgres' in db.get('Engine', '').lower()]

        if not postgres_dbs:
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

        with open("postgres_report.md", "w") as f:
            f.write(final_report_content)
        
        return f"Consolidated report for {len(postgres_dbs)} PostgreSQL instance(s) generated and saved to postgres_report.md."
    except Exception as e:
        print(f"ERROR in PostgreSQL Agent: {e}")
        import traceback
        traceback.print_exc()
        return f"An error occurred in the PostgreSQL agent: {e}"

# --- Agent Definition ---
postgres_dms_agent = LlmAgent(
    name="PostgreSQLDMSCheckerAgent",
    model=os.getenv("MODEL"),
    instruction="""You are an expert on AWS RDS for PostgreSQL and Google Cloud DMS.
    Your task is to fulfill a user's request to check their RDS instances for DMS compatibility.
    Call the `discover_and_generate_postgres_reports` tool, passing the user's original prompt.
    Your final output must be the full, consolidated report generated by the tool.
    """,
    description="Handles all requests for checking AWS RDS for PostgreSQL instances. It automatically discovers all PostgreSQL instances and generates a consolidated DMS pre-requisite report.",
    tools=[
        discover_and_generate_postgres_reports,
    ],
)