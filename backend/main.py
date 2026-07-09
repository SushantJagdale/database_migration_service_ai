from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from root_agent.agent import root_agent
from root_agent.dbmigration.dbmigration_agent import dbmigration_dms_agent, get_secret
from root_agent.aws_utils import reset_aws_session
from database_validator import validate_database_metrics
import asyncio
from google.genai import types
from google.adk.runners import InMemoryRunner
import os
import json
import subprocess
import logging
import sys
from io import StringIO
import uvicorn
from dotenv import load_dotenv
import google.generativeai as genai

# Load environment variables from a .env file
load_dotenv()

# --- Add this block to enable debug logging ---
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)

try:
    # Try to use API key if available (for backwards compatibility)
    api_key = os.getenv("GOOGLE_API_KEY")
    if api_key:
        genai.configure(api_key=api_key)
    else:
        # Use Application Default Credentials (recommended)
        print("[INFO] Using Application Default Credentials for Gemini authentication")
        # genai.Client() will automatically use ADC
except Exception as e:
    print(f"[WARNING] Error configuring Gemini: {e}")
    print("[INFO] Will attempt to use Application Default Credentials")


app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# Create the artifacts directory if it doesn't exist
artifacts_dir = os.path.join(os.getcwd(), "artifacts")
os.makedirs(artifacts_dir, exist_ok=True)

# Mount the artifacts directory to serve static files
app.mount("/artifacts", StaticFiles(directory=artifacts_dir), name="artifacts")


class ConfigureRequest(BaseModel):
    aws_account_id: str
    aws_access_key_id: str
    aws_secret_access_key: str

@app.post('/configure')
async def configure_aws(payload: ConfigureRequest):
    """
    This endpoint receives AWS credentials and account ID, and sets them as environment variables.
    """
    try:
        if not all([payload.aws_account_id, payload.aws_access_key_id, payload.aws_secret_access_key]):
            logging.error("Missing AWS credentials or Account ID in request body.")
            raise HTTPException(status_code=400, detail="Missing AWS credentials or Account ID.")

        os.environ['AWS_ACCOUNT_ID'] = payload.aws_account_id
        os.environ['AWS_ACCESS_KEY_ID'] = payload.aws_access_key_id
        os.environ['AWS_SECRET_ACCESS_KEY'] = payload.aws_secret_access_key
        
        # Clear Boto3 session cache to pick up the new credentials
        reset_aws_session()
        
        logging.info("AWS credentials and Account ID configured successfully.")
        return {"message": "AWS credentials and Account ID configured successfully."}
    except Exception as e:
        logging.exception("An error occurred during AWS configuration.")
        raise HTTPException(status_code=500, detail=str(e))

@app.post('/discover')
async def discover_databases(request: Request):
    """
    This endpoint triggers the root_agent to discover databases.
    It uses AWS credentials from the environment.
    """
    # AWS credentials are now expected to be in the environment
    if 'AWS_ACCESS_KEY_ID' not in os.environ or 'AWS_SECRET_ACCESS_KEY' not in os.environ:
        raise HTTPException(status_code=500, detail="AWS credentials are not configured in the backend environment.")

    try:
        body = await request.json()
        prompt = body.get("prompt")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body.")

    if not prompt:
        raise HTTPException(status_code=400, detail="Missing prompt")

    # Clear old reports from both workspace root and backend directory to ensure no stale data persists
    search_dirs = [
        os.getcwd(),
        os.path.join(os.getcwd(), "backend") if not os.getcwd().endswith("backend") else None,
    ]
    search_dirs = list(set([d for d in search_dirs if d and os.path.exists(d)]))
    
    for filename in ["mysql_report.md", "postgres_report.md"]:
        for s_dir in search_dirs:
            full_path = os.path.join(s_dir, filename)
            if os.path.exists(full_path):
                try:
                    os.remove(full_path)
                    logging.info(f"Deleted old report file: {full_path}")
                except Exception as io_err:
                    logging.warning(f"Could not remove old report file {full_path}: {io_err}")

    try:
        # Run the agent asynchronously
        result = await run_agent(prompt)
        report_path = result.get("report_path")
        if report_path:
            report_path = report_path.strip()
        if report_path and os.path.exists(report_path):
            scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
            host = request.headers.get("host", request.url.hostname)
            base_url = f"{scheme}://{host}"
            report_url = f"{base_url}/artifacts/{os.path.basename(report_path)}"
            
            # Extract instances list for frontend dropdowns
            from root_agent.report_generator import parse_md_report, find_report_file
            
            mysql_file = find_report_file("mysql_report.md")
            postgres_file = find_report_file("postgres_report.md")
            
            mysql_data = parse_md_report(mysql_file) if os.path.exists(mysql_file) else []
            postgres_data = parse_md_report(postgres_file) if os.path.exists(postgres_file) else []
            
            instances = []
            for r in mysql_data + postgres_data:
                metadata = r.get("metadata", {})
                inst_id = metadata.get("DBInstanceIdentifier")
                region = metadata.get("Region")
                engine = metadata.get("Engine")
                if inst_id:
                    instances.append({
                        "instance_id": inst_id,
                        "region": region or "us-east-1",
                        "engine": engine or "mysql"
                    })
            
            return {
                "report_url": report_url,
                "instances": instances
            }
        else:
            raise HTTPException(status_code=500, detail={"error": "Could not generate report.", "details": result})
    except Exception as e:
        logging.exception("An error occurred while running the agent.")
        raise HTTPException(status_code=500, detail={"error": str(e), "logs": "Check backend logs for more details."})

@app.post('/configuredms')
async def configure_dms(request: Request):
    """
    This endpoint triggers the dbmigration_dms_agent to configure connection profiles,
    create DMS migration jobs, check status, or promote databases.
    """
    try:
        body = await request.json()
        prompt = body.get("prompt")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body.")

    if not prompt:
        raise HTTPException(status_code=400, detail="Missing prompt")

    try:
        # Run the agent asynchronously
        result = await run_dbmigration_agent(prompt)
        return result
    except Exception as e:
        logging.exception("An error occurred while running the DMS agent.")
        raise HTTPException(status_code=500, detail={"error": str(e), "logs": "Check backend logs for more details."})

async def run_dbmigration_agent(prompt: str):
    """
    Initializes the runner, creates a session, and runs the dbmigration agent with the user's prompt,
    capturing and returning logs.
    """
    # Redirect stdout and stderr to capture logs
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    sys.stdout = captured_stdout = StringIO()
    sys.stderr = captured_stderr = StringIO()

    runner = InMemoryRunner(
        agent=dbmigration_dms_agent,
        app_name="db_migration_app",
    )
    session = await runner.session_service.create_session(
        app_name="db_migration_app", user_id="user"
    )

    content = types.Content(role='user', parts=[types.Part.from_text(text=prompt)])

    final_response = ""
    try:
        async for event in runner.run_async(
            user_id="user",
            session_id=session.id,
            new_message=content,
        ):
            if event.content and event.content.parts and event.content.parts[0].text:
                final_response = event.content.parts[0].text
    finally:
        # Restore stdout and stderr
        sys.stdout = old_stdout
        sys.stderr = old_stderr

    logs = captured_stdout.getvalue() + "\n" + captured_stderr.getvalue()
    print({"output": final_response, "logs": logs})
    return {"output": final_response, "logs": logs}

async def run_agent(prompt: str):
    """
    Initializes the runner, creates a session, and runs the agent with the user's prompt,
    capturing and returning logs.
    """
    # Redirect stdout and stderr to capture logs
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    sys.stdout = captured_stdout = StringIO()
    sys.stderr = captured_stderr = StringIO()

    runner = InMemoryRunner(
        agent=root_agent,
        app_name="db_discovery_app",
    )
    session = await runner.session_service.create_session(
        app_name="db_discovery_app", user_id="user"
    )

    content = types.Content(role='user', parts=[types.Part.from_text(text=prompt)])

    final_response = ""
    try:
        async for event in runner.run_async(
            user_id="user",
            session_id=session.id,
            new_message=content,
        ):
            if event.content and event.content.parts and event.content.parts[0].text:
                final_response = event.content.parts[0].text
    finally:
        # Restore stdout and stderr
        sys.stdout = old_stdout
        sys.stderr = old_stderr

    logs = captured_stdout.getvalue() + "\n" + captured_stderr.getvalue()
    print({"output": final_response, "logs": logs})
    return {"report_path": final_response, "logs": logs}

class ValidateRequest(BaseModel):
    instance_id: str
    engine: str

def get_target_instance_ip(instance_id: str) -> str:
    """
    Finds the IP address of the target Cloud SQL instance.
    Checks for '{instance_id}' first, then '{instance_id}-tgt'.
    Returns the PRIVATE IP if available, otherwise PRIMARY (public) IP.
    """
    project_id = os.getenv("GCP_PROJECT_ID") or os.getenv("PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
    
    # Try names
    names_to_try = [instance_id, f"{instance_id}-tgt"]
    
    for name in names_to_try:
        cmd = ["gcloud", "sql", "instances", "describe", name, f"--project={project_id}", "--format=json"]
        logging.info(f"Running command to describe SQL instance: {' '.join(cmd)}")
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            instance_data = json.loads(result.stdout)
            ip_addresses = instance_data.get("ipAddresses", [])
            
            # Find private IP first
            for ip in ip_addresses:
                if ip.get("type") == "PRIVATE":
                    logging.info(f"Found private IP for Cloud SQL instance '{name}': {ip.get('ipAddress')}")
                    return ip.get("ipAddress")
            
            # Fallback to primary public IP
            for ip in ip_addresses:
                if ip.get("type") == "PRIMARY":
                    logging.info(f"Found primary IP for Cloud SQL instance '{name}': {ip.get('ipAddress')}")
                    return ip.get("ipAddress")
                    
        except subprocess.CalledProcessError as err:
            logging.warning(f"Could not describe Cloud SQL instance '{name}': {err.stderr.strip()}")
        except Exception as e:
            logging.error(f"Error parsing Cloud SQL instance details: {e}")
            
    raise Exception(f"Could not find running Cloud SQL instance or resolve IP for: {instance_id}")

@app.post('/validate')
async def validate_database_endpoint(payload: ValidateRequest):
    """
    Connects to the target Cloud SQL instance, counts tables, schemas, and rows,
    and returns a summary report.
    """
    try:
        if not payload.instance_id or not payload.engine:
            raise HTTPException(status_code=400, detail="Missing instance_id or engine.")
            
        instance_id = payload.instance_id
        engine = payload.engine.lower()
        
        # 1. Resolve host IP of the target Cloud SQL instance
        try:
            target_ip = get_target_instance_ip(instance_id)
        except Exception as resolve_err:
            logging.exception("Failed to resolve target IP address.")
            raise HTTPException(status_code=404, detail=str(resolve_err))
            
        # 2. Fetch the password from Secret Manager
        try:
            pass_secret = f"{instance_id}_password"
            db_password = get_secret(pass_secret)
        except Exception as secret_err:
            logging.exception("Failed to fetch password from Secret Manager.")
            raise HTTPException(status_code=500, detail=f"Failed to fetch database credentials from Secret Manager: {secret_err}")
            
        # 3. Determine connection properties
        is_postgres = "postgres" in engine
        db_user = "postgres" if is_postgres else "root"
        db_port = 5432 if is_postgres else 3306
        
        # 4. Perform direct database metrics queries
        logging.info(f"Triggering direct validation on {engine} target at {target_ip}:{db_port}")
        validation_results = validate_database_metrics(
            engine=engine,
            host=target_ip,
            port=db_port,
            user=db_user,
            password=db_password
        )
        
        if "error" in validation_results:
            raise HTTPException(status_code=500, detail=validation_results["error"])
            
        return validation_results
        
    except HTTPException as http_err:
        raise http_err
    except Exception as e:
        logging.exception("Unexpected error during database validation.")
        raise HTTPException(status_code=500, detail=f"Unexpected validation error: {str(e)}")

class DmsStatusRequest(BaseModel):
    job_name: str
    region: str

def get_dms_job_status(job_name: str, region: str) -> dict:
    try:
        from root_agent.dbmigration.dbmigration_agent import check_dms_status
        status_md = check_dms_status(job_name, region)
        state = "UNKNOWN"
        phase = "UNKNOWN"
        for line in status_md.split("\n"):
            if "State" in line:
                state = line.split(":")[-1].strip().replace("**", "").replace("*", "")
            elif "Phase" in line:
                phase = line.split(":")[-1].strip().replace("**", "").replace("*", "")
        
        if state != "UNKNOWN" and "Failed to check" not in status_md:
            return {
                "configured": True,
                "state": state,
                "phase": phase,
                "lag": 0,
                "promoted": state == "COMPLETED" or state == "PROMOTED",
                "job_name": job_name,
                "region": region
            }
    except Exception as e:
        logging.warning(f"Failed to query real DMS status: {e}")

    return {
        "configured": False,
        "state": "NONE",
        "phase": "NONE",
        "lag": 0,
        "promoted": False,
        "job_name": job_name,
        "region": region
    }

@app.post("/dms/status")
async def dms_status_endpoint(payload: DmsStatusRequest):
    try:
        status = get_dms_job_status(payload.job_name, payload.region)
        return status
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == '__main__':
    uvicorn.run(app, host='0.0.0.0', port=8091)