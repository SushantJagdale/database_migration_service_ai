import logging
import pg8000
import pymysql
from typing import Dict, List, Any

# Configure logging
logger = logging.getLogger("database_validator")

def validate_postgres(host: str, port: int, user: str, password: str) -> Dict[str, Any]:
    """
    Connects to target PostgreSQL database, discovers user databases,
    schemas, tables, and counts rows.
    """
    results = {"databases": []}
    
    # 1. Connect to default 'postgres' database to find other databases
    conn = None
    try:
        logger.info(f"Connecting to Postgres at {host}:{port} under user '{user}' to list databases...")
        conn = pg8000.connect(host=host, port=port, user=user, password=password, database="postgres", timeout=15)
        cursor = conn.cursor()
        
        cursor.execute("SELECT datname FROM pg_database WHERE datistemplate = false AND datname NOT IN ('postgres', 'cloudsqladmin');")
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
                WHERE schema_name NOT IN ('pg_catalog', 'information_schema')
                  AND schema_name NOT LIKE 'pg_temp_%'
                  AND schema_name NOT LIKE 'pg_toast_%';
            """)
            schemas = [row[0] for row in db_cursor.fetchall()]
            
            for schema in schemas:
                schema_info = {"name": schema, "tables": []}
                
                # List tables in this schema
                db_cursor.execute("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = %s 
                      AND table_type = 'BASE TABLE';
                """, (schema,))
                tables = [row[0] for row in db_cursor.fetchall()]
                
                for table in tables:
                    # Count rows in each table
                    row_count = 0
                    try:
                        db_cursor.execute(f'SELECT COUNT(*) FROM "{schema}"."{table}";')
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
    Connects to target MySQL database, discovers databases, tables, and counts rows.
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
            # We map database to a default schema structure for consistency.
            db_info = {"name": db_name, "schemas": [{"name": db_name, "tables": []}]}
            
            # Select the database
            cursor.execute(f"USE `{db_name}`;")
            
            # List tables
            cursor.execute("SHOW TABLES;")
            tables = [row[0] for row in cursor.fetchall()]
            
            for table in tables:
                row_count = 0
                try:
                    cursor.execute(f"SELECT COUNT(*) FROM `{table}`;")
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

def validate_database_metrics(engine: str, host: str, port: int, user: str, password: str) -> Dict[str, Any]:
    """
    Dispatcher to validate database metrics based on engine type.
    """
    if "postgres" in engine.lower():
        return validate_postgres(host, port, user, password)
    elif "mysql" in engine.lower():
        return validate_mysql(host, port, user, password)
    else:
        return {"error": f"Unsupported database engine for direct validation: {engine}"}
