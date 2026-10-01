import logging
import pg8000
import pymysql
from typing import Dict, List, Any, Optional

# Configure logging
logger = logging.getLogger("database_validator")


def _quote_pg_ident(ident: str) -> str:
    """Safely quotes a PostgreSQL identifier by doubling any embedded double-quotes."""
    return '"' + str(ident).replace('"', '""') + '"'


def _quote_mysql_ident(ident: str) -> str:
    """Safely quotes a MySQL identifier by doubling any embedded backticks."""
    return '`' + str(ident).replace('`', '``') + '`'


def validate_postgres(host: str, port: int, user: str, password: str) -> Dict[str, Any]:
    """
    Connects to a PostgreSQL database instance, discovers user databases,
    schemas, tables, sequences, and counts rows.
    """
    results = {"databases": []}
    
    # 1. Connect to default 'postgres' database to find other databases
    conn = None
    try:
        logger.info(f"Connecting to Postgres at {host}:{port} under user '{user}' to list databases...")
        conn = pg8000.connect(host=host, port=port, user=user, password=password, database="postgres", timeout=15)
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT datname FROM pg_database "
            "WHERE datistemplate = false AND datname NOT IN ('postgres', 'cloudsqladmin', 'rdsadmin');"
        )
        db_names = [row[0] for row in cursor.fetchall()]
        cursor.close()
        conn.close()
    except Exception as e:
        logger.exception("Failed to query database list from PostgreSQL.")
        return {"error": f"Failed to connect to PostgreSQL admin instance: {e}"}

    # 2. Query details from each discovered database
    for db_name in db_names:
        db_info = {"name": db_name, "schemas": []}
        db_conn = None
        try:
            logger.info(f"Connecting to database '{db_name}' on {host}...")
            db_conn = pg8000.connect(host=host, port=port, user=user, password=password, database=db_name, timeout=15)
            db_cursor = db_conn.cursor()
            
            # Find user-created schemas
            db_cursor.execute("""
                SELECT schema_name 
                FROM information_schema.schemata 
                WHERE schema_name NOT IN ('pg_catalog', 'information_schema', 'pglogical')
                  AND schema_name NOT LIKE 'pg_temp_%'
                  AND schema_name NOT LIKE 'pg_toast_%';
            """)
            schemas = [row[0] for row in db_cursor.fetchall()]
            
            for schema in schemas:
                schema_info = {"name": schema, "tables": [], "sequences_count": 0}
                
                # Count sequences in this schema
                try:
                    db_cursor.execute(
                        "SELECT COUNT(*) FROM information_schema.sequences WHERE sequence_schema = %s;",
                        (schema,)
                    )
                    seq_row = db_cursor.fetchone()
                    schema_info["sequences_count"] = int(seq_row[0]) if seq_row else 0
                except Exception:
                    schema_info["sequences_count"] = 0

                # List tables in this schema
                db_cursor.execute("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = %s 
                      AND table_type = 'BASE TABLE';
                """, (schema,))
                tables = [row[0] for row in db_cursor.fetchall()]
                
                for table in tables:
                    row_count = 0
                    try:
                        safe_schema = _quote_pg_ident(schema)
                        safe_table = _quote_pg_ident(table)
                        db_cursor.execute(f"SELECT COUNT(*) FROM {safe_schema}.{safe_table};")
                        row_count = db_cursor.fetchone()[0]
                    except Exception as count_err:
                        logger.warning(f"Could not count rows for table {schema}.{table}: {count_err}")
                        row_count = -1  # Indicates error retrieving count
                        
                    schema_info["tables"].append({
                        "name": table,
                        "rows": row_count
                    })
                
                db_info["schemas"].append(schema_info)
            
            db_cursor.close()
            db_conn.close()
            results["databases"].append(db_info)
            
        except Exception as db_err:
            logger.exception(f"Failed to query database details for '{db_name}'.")
            db_info["error"] = str(db_err)
            results["databases"].append(db_info)
            if db_conn:
                try:
                    db_conn.close()
                except Exception:
                    pass

    return results


def validate_mysql(host: str, port: int, user: str, password: str) -> Dict[str, Any]:
    """
    Connects to a MySQL database instance, discovers databases, tables, and counts rows.
    """
    results = {"databases": []}
    conn = None
    try:
        logger.info(f"Connecting to MySQL at {host}:{port} under user '{user}'...")
        conn = pymysql.connect(
            host=host, 
            port=port, 
            user=user, 
            password=password, 
            charset='utf8mb4',
            connect_timeout=15
        )
        cursor = conn.cursor()
        
        # Get list of databases (schemas)
        cursor.execute("SHOW DATABASES;")
        db_names = [row[0] for row in cursor.fetchall()]
        
        # Exclude system databases
        excluded_dbs = {'information_schema', 'mysql', 'performance_schema', 'sys'}
        user_dbs = [db for db in db_names if db not in excluded_dbs]
        
        for db_name in user_dbs:
            # Under MySQL, "schemas" and "databases" are synonymous.
            db_info = {"name": db_name, "schemas": [{"name": db_name, "tables": []}]}
            
            safe_db = _quote_mysql_ident(db_name)
            cursor.execute(f"USE {safe_db};")
            
            # List tables
            cursor.execute("SHOW FULL TABLES WHERE Table_type = 'BASE TABLE';")
            tables = [row[0] for row in cursor.fetchall()]
            
            for table in tables:
                row_count = 0
                try:
                    safe_table = _quote_mysql_ident(table)
                    cursor.execute(f"SELECT COUNT(*) FROM {safe_table};")
                    row_count = cursor.fetchone()[0]
                except Exception as count_err:
                    logger.warning(f"Could not count rows for table {db_name}.{table}: {count_err}")
                    row_count = -1
                
                db_info["schemas"][0]["tables"].append({
                    "name": table,
                    "rows": row_count
                })
                
            results["databases"].append(db_info)
            
        cursor.close()
        conn.close()
    except Exception as e:
        logger.exception("Failed to query database details from MySQL.")
        return {"error": f"Failed to connect to MySQL instance: {e}"}
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
                
    return results


def _merge_source_and_target_metrics(
    target_results: Dict[str, Any],
    source_results: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Merges source RDS row counts with target Cloud SQL row counts to produce
    a side-by-side data parity report.
    """
    if "error" in target_results:
        return target_results

    source_lookup: Dict[tuple, int] = {}
    source_connected = bool(source_results and "databases" in source_results and "error" not in source_results)

    if source_connected and source_results:
        for s_db in source_results.get("databases", []):
            db_name = s_db.get("name")
            for s_sch in s_db.get("schemas", []):
                sch_name = s_sch.get("name")
                for s_tbl in s_sch.get("tables", []):
                    tbl_name = s_tbl.get("name")
                    source_lookup[(db_name, sch_name, tbl_name)] = s_tbl.get("rows", -1)

    total_tables = 0
    matched_tables = 0
    mismatched_tables = 0

    for t_db in target_results.get("databases", []):
        db_name = t_db.get("name")
        for t_sch in t_db.get("schemas", []):
            sch_name = t_sch.get("name")
            seen_tables = set()
            for t_tbl in t_sch.get("tables", []):
                tbl_name = t_tbl.get("name")
                seen_tables.add(tbl_name)
                total_tables += 1
                t_rows = t_tbl.get("rows", -1)
                t_tbl["target_rows"] = t_rows

                if source_connected:
                    s_rows = source_lookup.get((db_name, sch_name, tbl_name))
                    t_tbl["source_rows"] = s_rows
                    if s_rows is not None and s_rows >= 0 and t_rows >= 0:
                        diff = t_rows - s_rows
                        t_tbl["diff"] = diff
                        if diff == 0:
                            t_tbl["status"] = "MATCH"
                            matched_tables += 1
                        else:
                            t_tbl["status"] = "MISMATCH"
                            mismatched_tables += 1
                    else:
                        t_tbl["diff"] = None
                        t_tbl["status"] = "TARGET_ONLY"
                else:
                    t_tbl["source_rows"] = None
                    t_tbl["diff"] = None
                    t_tbl["status"] = "VERIFIED" if t_rows >= 0 else "ERROR"
                    if t_rows >= 0:
                        matched_tables += 1

            # Check if any source tables in this schema are missing on target
            if source_connected:
                for (s_db_n, s_sch_n, s_tbl_n), s_rows in source_lookup.items():
                    if s_db_n == db_name and s_sch_n == sch_name and s_tbl_n not in seen_tables:
                        total_tables += 1
                        mismatched_tables += 1
                        t_sch["tables"].append({
                            "name": s_tbl_n,
                            "rows": 0,
                            "target_rows": 0,
                            "source_rows": s_rows,
                            "diff": -s_rows if s_rows >= 0 else None,
                            "status": "MISSING_ON_TARGET",
                        })

    parity_pct = round((matched_tables / total_tables) * 100.0, 1) if total_tables > 0 else 100.0
    target_results["parity_summary"] = {
        "source_connected": source_connected,
        "total_tables": total_tables,
        "matched_tables": matched_tables,
        "mismatched_tables": mismatched_tables,
        "parity_percentage": parity_pct,
    }
    return target_results


def validate_database_metrics(
    engine: str,
    host: str,
    port: int,
    user: str,
    password: str,
    source_host: Optional[str] = None,
    source_port: Optional[int] = None,
    source_user: Optional[str] = None,
    source_password: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Dispatcher to validate target database metrics and optionally compare side-by-side
    against the source RDS instance for 100% data parity verification.
    """
    engine_lower = engine.lower()
    if "postgres" in engine_lower:
        target_res = validate_postgres(host, port, user, password)
        source_res = None
        if source_host and source_user and source_password:
            try:
                source_res = validate_postgres(source_host, source_port or 5432, source_user, source_password)
            except Exception as e:
                logger.warning(f"Could not connect to source Postgres for side-by-side comparison: {e}")
        return _merge_source_and_target_metrics(target_res, source_res)
    elif "mysql" in engine_lower:
        target_res = validate_mysql(host, port, user, password)
        source_res = None
        if source_host and source_user and source_password:
            try:
                source_res = validate_mysql(source_host, source_port or 3306, source_user, source_password)
            except Exception as e:
                logger.warning(f"Could not connect to source MySQL for side-by-side comparison: {e}")
        return _merge_source_and_target_metrics(target_res, source_res)
    else:
        return {"error": f"Unsupported database engine for direct validation: {engine}"}
