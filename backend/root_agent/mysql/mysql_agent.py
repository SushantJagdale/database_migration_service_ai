from ..aws_utils import (
    get_rds_metadata,
    get_parameter_group_settings,
    list_all_rds_dbs,
    get_specific_db_parameter,
    get_cluster_parameter_group_settings,
    get_rds_cloudwatch_metrics,
)
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
            if engine_version.startswith('5.7') or engine_version.startswith('8.0') or engine_version.startswith('8.4'):
                return f"PASS: Compatible ({engine_version})."
            else:
                return f"FAIL: Not compatible ({engine_version}). Must be 5.7+, 8.0+, or 8.4+."
        return "FAIL: Could not retrieve RDS metadata."
    except Exception as e:
        return f"Error checking MySQL version: {e}"

def check_mysql_replication_params(instance_id: str, region: str) -> str:
    """Checks critical MySQL replication parameters (log_bin, binlog_format, gtid_mode)."""
    try:
        metadata = get_rds_metadata(instance_id, region)
        if not metadata or not metadata.get('DBParameterGroups'):
            return "FAIL: Could not retrieve parameter group for the instance."
        group_name = metadata['DBParameterGroups'][0]['DBParameterGroupName']
        params = get_parameter_group_settings(group_name, region) or []

        # Also check cluster parameter group if this is an Aurora MySQL instance
        cluster_id = metadata.get('DBClusterIdentifier')
        if cluster_id:
            _, cluster_params = get_cluster_parameter_group_settings(cluster_id, region)
            if cluster_params:
                params = cluster_params + params

        if not params:
            return f"FAIL: Could not retrieve parameters for group {group_name}."
        
        log_bin_param = next((p for p in params if p['ParameterName'] == 'log_bin'), None)
        binlog_format_param = next((p for p in params if p['ParameterName'] == 'binlog_format'), None)
        gtid_mode_param = next((p for p in params if p['ParameterName'] == 'gtid_mode'), None)
        enforce_gtid_param = next((p for p in params if p['ParameterName'] == 'enforce_gtid_consistency'), None)

        # Check BackupRetentionPeriod to determine log_bin status for RDS MySQL
        backup_retention = metadata.get('BackupRetentionPeriod', 0)
        if backup_retention > 0:
            log_bin = 'ON'
        else:
            log_bin = log_bin_param.get('ParameterValue', 'OFF') if log_bin_param else 'OFF'

        binlog_format = binlog_format_param.get('ParameterValue', 'Not Set') if binlog_format_param else 'Not Set'
        gtid_mode = gtid_mode_param.get('ParameterValue', 'Not Set') if gtid_mode_param else 'Not Set'
        enforce_gtid = enforce_gtid_param.get('ParameterValue', 'Not Set') if enforce_gtid_param else 'Not Set'

        results = []
        if log_bin == 'ON':
            results.append(f"PASS: log_bin is ON (BackupRetentionPeriod={backup_retention}d).")
        else:
            results.append(f"FAIL: log_bin is '{log_bin}'. Enable automated backups (BackupRetentionPeriod > 0) to turn on binary logging.")
        
        if binlog_format == 'ROW':
            results.append("PASS: binlog_format is ROW.")
        else:
            results.append(f"FAIL: binlog_format is '{binlog_format}'. It must be 'ROW'.")

        if gtid_mode in ['ON', 'ON_PERMISSIVE'] and enforce_gtid == 'ON':
            results.append(f"PASS: GTID replication ready (gtid_mode={gtid_mode}, enforce_gtid_consistency={enforce_gtid}).")
        else:
            results.append(f"INFO: GTID params (gtid_mode={gtid_mode}, enforce_gtid_consistency={enforce_gtid}). Recommended to set both to ON for resilient CDC.")
            
        results.append("INFO: binlog_retention_hours cannot be read from Parameter Groups. Ensure CALL mysql.rds_set_configuration('binlog retention hours', 24); (or 48) is configured.")
            
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
            return f"WARNING: max_allowed_packet is '{param.get('ParameterValue', 'Not Set')}'. Small values can cause Error 1153 during Full Dump of BLOB/TEXT rows."
        else:
            return "INFO: max_allowed_packet is not explicitly set. Consider setting it to 256M (268435456) or higher."
    except Exception as e:
        return f"Error checking max_allowed_packet: {e}"

def check_mysql_cloudwatch_sizing(instance_id: str, region: str) -> str:
    """Evaluates 7-day CloudWatch CPU & IOPS metrics for right-sizing recommendations."""
    try:
        cw = get_rds_cloudwatch_metrics(instance_id, region)
        if not cw:
            return "INFO: CloudWatch metrics unavailable; 1:1 instance class sizing will be used."
        cpu_avg = cw.get("CPUUtilization_Avg", 0)
        cpu_max = cw.get("CPUUtilization_Max", 0)
        read_iops = cw.get("ReadIOPS_Max", 0)
        write_iops = cw.get("WriteIOPS_Max", 0)
        summary = f"7d CPU Avg: {cpu_avg}%, Max: {cpu_max}% | Peak IOPS (R/W): {read_iops}/{write_iops}"
        if cpu_max > 0 and cpu_max < 25.0:
            return f"PASS: {summary}\nINFO: Low peak CPU (<25%) detected. Candidate for Cloud SQL tier right-sizing (cost optimization)."
        elif cpu_max > 80.0:
            return f"WARNING: {summary}\nINFO: High CPU utilization (>80%) detected. Consider Cloud SQL Enterprise Plus or scaling up vCPUs."
        return f"PASS: {summary}"
    except Exception as e:
        return f"INFO: Could not evaluate CloudWatch sizing metrics: {e}"

def check_mysql_source_schema_readiness(instance_id: str, region: str) -> str:
    """
    Attempts a direct, read-only SQL pre-flight check on the source MySQL RDS instance
    if credentials exist in Secret Manager and the endpoint is reachable.
    Checks binlog retention hours, tables missing Primary Keys, and non-InnoDB tables.
    """
    try:
        metadata = get_rds_metadata(instance_id, region)
        endpoint = metadata.get("Endpoint", {}) if metadata else {}
        host = endpoint.get("Address")
        port = int(endpoint.get("Port", 3306))
        if not host:
            return "INFO: Source endpoint not available for live SQL schema audit."

        from ..dbmigration.dbmigration_agent import get_secret
        try:
            user = get_secret(f"{instance_id}_user")
            password = get_secret(f"{instance_id}_password")
        except Exception:
            return "INFO: Secret Manager credentials not yet configured for live SQL schema audit (Primary Key & InnoDB check)."

        import pymysql
        conn = pymysql.connect(host=host, port=port, user=user, password=password, connect_timeout=4, read_timeout=6)
        cursor = conn.cursor()
        findings = []

        # 1. Check RDS binlog retention hours
        try:
            cursor.execute("CALL mysql.rds_show_configuration;")
            rows = cursor.fetchall()
            binlog_ret = next((r[1] for r in rows if r and str(r[0]).lower() == "binlog retention hours"), None)
            if binlog_ret is not None and str(binlog_ret).upper() != "NULL" and int(binlog_ret) >= 24:
                findings.append(f"PASS: Live RDS binlog retention hours is {binlog_ret}h.")
            else:
                findings.append(f"FAIL: Live RDS binlog retention hours is '{binlog_ret}'. Run CALL mysql.rds_set_configuration('binlog retention hours', 48); to prevent Error 1236 during CDC.")
        except Exception:
            pass

        # 2. Check non-InnoDB tables in user schemas
        cursor.execute("""
            SELECT TABLE_SCHEMA, TABLE_NAME, ENGINE
            FROM information_schema.TABLES
            WHERE TABLE_TYPE = 'BASE TABLE'
              AND TABLE_SCHEMA NOT IN ('mysql', 'information_schema', 'performance_schema', 'sys')
              AND ENGINE != 'InnoDB';
        """)
        non_innodb = cursor.fetchall()
        if non_innodb:
            sample = ", ".join(f"{r[0]}.{r[1]} ({r[2]})" for r in non_innodb[:5])
            findings.append(f"FAIL: Found {len(non_innodb)} non-InnoDB table(s): {sample}. Convert to InnoDB before DMS Full Dump.")
        else:
            findings.append("PASS: All user tables use transactional InnoDB storage engine.")

        # 3. Check tables missing Primary Keys (causes severe CDC lag)
        cursor.execute("""
            SELECT t.TABLE_SCHEMA, t.TABLE_NAME
            FROM information_schema.TABLES t
            LEFT JOIN information_schema.TABLE_CONSTRAINTS c
              ON t.TABLE_SCHEMA = c.TABLE_SCHEMA
             AND t.TABLE_NAME = c.TABLE_NAME
             AND c.CONSTRAINT_TYPE = 'PRIMARY KEY'
            WHERE t.TABLE_TYPE = 'BASE TABLE'
              AND t.TABLE_SCHEMA NOT IN ('mysql', 'information_schema', 'performance_schema', 'sys')
              AND c.CONSTRAINT_NAME IS NULL;
        """)
        missing_pk = cursor.fetchall()
        if missing_pk:
            sample = ", ".join(f"{r[0]}.{r[1]}" for r in missing_pk[:5])
            findings.append(f"WARNING: Found {len(missing_pk)} table(s) without Primary Key ({sample}). May cause CDC replication lag.")
        else:
            findings.append("PASS: All user tables have Primary Keys defined.")

        cursor.close()
        conn.close()
        return "\n".join(findings)
    except Exception:
        return "INFO: Live SQL schema check skipped (source RDS in private VPC or unreachable from discovery host). Ensure all user tables use InnoDB and have Primary Keys."

def build_mysql_remediation_suggestions(instance_id: str, region: str, metadata: dict, validation_results: dict) -> str:
    """Builds actionable AWS CLI and SQL remediation commands when checks fail or warn."""
    group_name = "your-parameter-group"
    if metadata and metadata.get("DBParameterGroups"):
        group_name = metadata["DBParameterGroups"][0].get("DBParameterGroupName", group_name)

    cmds = []
    rep_status = validation_results.get("Replication Params", "")
    pkt_status = validation_results.get("Packet Size", "")
    schema_status = validation_results.get("Schema & Binlog Readiness", "")

    if "FAIL: binlog_format" in rep_status or "WARNING: max_allowed_packet" in pkt_status:
        cmds.append(
            f"# 1. Update RDS Parameter Group ({group_name}) for DMS compatibility:\n"
            f"aws rds modify-db-parameter-group \\\n"
            f"  --db-parameter-group-name {group_name} \\\n"
            f"  --region {region} \\\n"
            f"  --parameters \"ParameterName=binlog_format,ParameterValue=ROW,ApplyMethod=immediate\" "
            f"\"ParameterName=max_allowed_packet,ParameterValue=268435456,ApplyMethod=immediate\""
        )
    if "FAIL: log_bin" in rep_status:
        cmds.append(
            f"# Enable automated backups on RDS instance to activate binary logging:\n"
            f"aws rds modify-db-instance \\\n"
            f"  --db-instance-identifier {instance_id} \\\n"
            f"  --region {region} \\\n"
            f"  --backup-retention-period 7 \\\n"
            f"  --apply-immediately"
        )
    cmds.append(
        f"# Verify/Set RDS MySQL binlog retention to 48 hours and grant DMS replication privileges:\n"
        f"CALL mysql.rds_set_configuration('binlog retention hours', 48);\n"
        f"GRANT REPLICATION SLAVE, REPLICATION CLIENT, SELECT, RELOAD, SHOW VIEW, TRIGGER ON *.* TO '<migration_user>'@'%';\n"
        f"FLUSH PRIVILEGES;"
    )
    if "non-InnoDB" in schema_status:
        cmds.append("# Convert any MyISAM tables to InnoDB:\n# ALTER TABLE <schema>.<table> ENGINE=InnoDB;")

    return "\n\n".join(cmds)

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
        "Schema & Binlog Readiness": check_mysql_source_schema_readiness(instance_id, region),
        "CloudWatch Sizing & Telemetry": check_mysql_cloudwatch_sizing(instance_id, region),
    }
    suggestions = build_mysql_remediation_suggestions(instance_id, region, rds_metadata, validation_results)
    return generate_report("MySQL", rds_metadata, validation_results, suggestions)

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