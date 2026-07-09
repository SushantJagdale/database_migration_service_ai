from ..aws_utils import get_rds_metadata, get_parameter_group_settings, list_all_rds_dbs, get_specific_db_parameter
from google.adk.agents import Agent, LlmAgent
from ..report_generator import generate_report
import os
import asyncio
from typing import Optional
import subprocess
from dotenv import load_dotenv

load_dotenv()


# --- Tool Functions for a SINGLE MySQL Instance ---
def check_mysql_version(instance_id: str, region: str) -> str:
    """Checks the MySQL version of an RDS instance."""
    try:
        metadata = get_rds_metadata(instance_id, region)
        if metadata:
            engine_version = metadata.get('EngineVersion', 'Unknown')
            if engine_version.startswith('5.7') or engine_version.startswith('8.0'):
                return "PASS: Compatible."
            else:
                return "FAIL: Not compatible. Must be 5.7+ or 8.0+."
        return "FAIL: Could not retrieve RDS metadata."
    except Exception as e:
        return f"Error checking MySQL version: {e}"

def check_mysql_replication_params(instance_id: str, region: str) -> str:
    """Checks critical MySQL replication parameters (log_bin, binlog_format)."""
    try:
        metadata = get_rds_metadata(instance_id, region)
        if not metadata or not metadata.get('DBParameterGroups'):
            return "FAIL: Could not retrieve parameter group for the instance."
        group_name = metadata['DBParameterGroups'][0]['DBParameterGroupName']
        params = get_parameter_group_settings(group_name, region)
        if not params:
            return f"FAIL: Could not retrieve parameters for group {group_name}."
        
        log_bin_param = next((p for p in params if p['ParameterName'] == 'log_bin'), None)
        binlog_format_param = next((p for p in params if p['ParameterName'] == 'binlog_format'), None)
        binlog_retention_param = next((p for p in params if p['ParameterName'] in ['binlog_retention_hours', 'binlog_retention_period']), None)

        # Check BackupRetentionPeriod to determine log_bin status for RDS MySQL
        backup_retention = metadata.get('BackupRetentionPeriod', 0)
        if backup_retention > 0:
            log_bin = 'ON'
        else:
            log_bin = log_bin_param.get('ParameterValue', 'OFF') if log_bin_param else 'OFF'

        binlog_format = binlog_format_param.get('ParameterValue', 'Not Set') if binlog_format_param else 'Not Set'
        binlog_retention = binlog_retention_param.get('ParameterValue', 'Not Set') if binlog_retention_param else 'Not Set'

        results = []
        if log_bin == 'ON':
            results.append("PASS: log_bin is ON.")
        else:
            results.append(f"FAIL: log_bin is '{log_bin}'. It must be 'ON'.")
        
        if binlog_format == 'ROW':
            results.append("PASS: binlog_format is ROW.")
        else:
            results.append(f"FAIL: binlog_format is '{binlog_format}'. It must be 'ROW'.")
            
        # binlog_retention_hours is configured dynamically via stored procedure and not present in the RDS Parameter Group.
        # Since Boto3 cannot read it and we don't connect via SQL during discovery, we report it as an INFO advisory.
        results.append("INFO: binlog_retention_hours cannot be verified from the Parameter Group. Please ensure it is set to a non-zero value (e.g. 24).")
        results.append("Suggestion: Run CALL mysql.rds_set_configuration('binlog retention hours', 24); on the database to verify/set it.")
            
        return "\n".join(results)
    except Exception as e:
        return f"Error checking MySQL replication params: {e}"

def check_mysql_table_case(instance_id: str, region: str) -> str:
    """Checks the lower_case_table_names parameter."""
    try:
        metadata = get_rds_metadata(instance_id, region)
        if not metadata or not metadata.get('DBParameterGroups'):
            return "FAIL: Could not retrieve parameter group for the instance."
        group_name = metadata['DBParameterGroups'][0]['DBParameterGroupName']
        param = get_specific_db_parameter(group_name, region, 'lower_case_table_names')
        
        if param and param.get('ParameterValue') == '1':
            return "PASS: lower_case_table_names is set to 1 (case-insensitive)."
        elif param:
            return f"WARNING: lower_case_table_names is '{param.get('ParameterValue', 'Not Set')}'. Mismatches with the destination can cause issues."
        else:
            return "INFO: lower_case_table_names is not explicitly set. Defaults should be compatible."
    except Exception as e:
        return f"Error checking lower_case_table_names: {e}"

def check_mysql_packet_size(instance_id: str, region: str) -> str:
    """Checks the max_allowed_packet parameter."""
    try:
        metadata = get_rds_metadata(instance_id, region)
        if not metadata or not metadata.get('DBParameterGroups'):
            return "FAIL: Could not retrieve parameter group for the instance."
        group_name = metadata['DBParameterGroups'][0]['DBParameterGroupName']
        param = get_specific_db_parameter(group_name, region, 'max_allowed_packet')
        
        if param and int(param.get('ParameterValue', 0)) >= 268435456: # 256MB
            return f"PASS: max_allowed_packet is set to a reasonable size ({param.get('ParameterValue')})."
        elif param:
            return f"WARNING: max_allowed_packet is '{param.get('ParameterValue', 'Not Set')}'. Small values can cause issues with large data packets."
        else:
            return "INFO: max_allowed_packet is not explicitly set. Consider setting it to 256M or higher."
    except Exception as e:
        return f"Error checking max_allowed_packet: {e}"

def generate_single_mysql_report(instance_id: str, region: str) -> str:
    """Generates a pre-migration report for a single MySQL RDS instance."""
    rds_metadata = get_rds_metadata(instance_id, region)
    # Add the region to the metadata for the report
    if rds_metadata:
        rds_metadata['Region'] = region

    validation_results = {
        "Version Check": check_mysql_version(instance_id, region),
        "Replication Params": check_mysql_replication_params(instance_id, region),
        "Table Case Sensitivity": check_mysql_table_case(instance_id, region),
        "Packet Size": check_mysql_packet_size(instance_id, region),
    }
    # Suggestions are now implicitly part of the checks, so we pass an empty string.
    return generate_report("MySQL", rds_metadata, validation_results, "")

# --- Multi-Instance Orchestration ---
async def discover_and_generate_mysql_reports(user_prompt: str, region_name: Optional[str] = None) -> str:
    """
    Discovers all MySQL RDS instances, performs DMS checks, and generates a consolidated report.
    
    Args:
        user_prompt: The user's original query.
        region_name: Optional AWS region name (e.g. 'us-east-1', 'ap-south-1') to filter instances.
    """
    def sync_run():
        try:
            if region_name:
                print(f"MySQL Agent: Discovering RDS instances in region {region_name}...")
                all_dbs = list_all_rds_dbs(region_name=region_name)
            else:
                print("MySQL Agent: Discovering all RDS instances across all regions...")
                all_dbs = list_all_rds_dbs()
            mysql_dbs = [db for db in all_dbs if 'mysql' in db.get('Engine', '').lower()]

            backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            report_path = os.path.join(backend_dir, "mysql_report.md")

            if not mysql_dbs:
                with open(report_path, "w") as f:
                    f.write("")
                return "No MySQL RDS instances were found."

            print(f"MySQL Agent: Found {len(mysql_dbs)} MySQL instance(s). Generating reports...")
            
            final_report_content = ""
            
            for db in mysql_dbs:
                instance_id = db.get('DBInstanceIdentifier')
                region = db.get('Region')
                if not instance_id or not region:
                    continue
                
                print(f"MySQL Agent: Processing instance {instance_id} in {region}...")
                report_part = generate_single_mysql_report(instance_id, region)
                final_report_content += report_part

            with open(report_path, "w") as f:
                f.write(final_report_content)
            
            return f"Consolidated report for {len(mysql_dbs)} MySQL instance(s) generated and saved to {report_path}."
        except Exception as e:
            print(f"ERROR in MySQL Agent: {e}")
            import traceback
            traceback.print_exc()
            return f"An error occurred in the MySQL agent: {e}"

    return await asyncio.to_thread(sync_run)

# --- Agent Definition ---
mysql_dms_agent = LlmAgent(
    name="MySQLDMSCheckerAgent",
    model=os.getenv("MODEL"),
    instruction="""You are an expert on AWS RDS for MySQL and Google Cloud DMS.
    Your task is to fulfill a user's request to check their RDS instances for DMS compatibility.
    
    CRITICAL: Check if the user's prompt specifies checking database engines. If the user explicitly asks for only PostgreSQL or excludes MySQL, do NOT call the `discover_and_generate_mysql_reports` tool. Just respond saying that MySQL checks are skipped.
    Otherwise, call the `discover_and_generate_mysql_reports` tool, passing the user's original prompt.
    
    Determine the regional scope from the user's prompt and pass it as `region_name`:
    - If they specify a single region or city (e.g., "mumbai", "ap-south-1", "mumbai region"), resolve it to its official AWS region code (e.g., "ap-south-1").
    - If they specify a broader regional scope (e.g., "US region", "databases in US", "US regions"), resolve it to a wildcard pattern (e.g., "us-*").
    - If they specify Europe (e.g., "Europe region"), resolve it to "eu-*".
    - If they specify Asia, resolve it to "ap-*".
    - Otherwise (if no regional scope is specified), pass None.
    
    Your final output must be the full, consolidated report generated by the tool, or the skip message.

    You are an agent. Your internal name is `MySQLDMSCheckerAgent`. The description about you is: Handles all requests for checking AWS RDS for MySQL instances. It automatically discovers all MySQL instances and generates a consolidated DMS pre-requisite report.
    """,
    description="Handles all requests for checking AWS RDS for MySQL instances. It automatically discovers all MySQL instances and generates a consolidated DMS pre-requisite report.",
    tools=[
        discover_and_generate_mysql_reports,
    ],
)