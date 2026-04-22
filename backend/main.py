from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from root_agent.agent import root_agent
import asyncio
from google.genai import types
from google.adk.runners import InMemoryRunner
import os
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
            return {"report_url": report_url}
        else:
            raise HTTPException(status_code=500, detail={"error": "Could not generate report.", "details": result})
    except Exception as e:
        logging.exception("An error occurred while running the agent.")
        raise HTTPException(status_code=500, detail={"error": str(e), "logs": "Check backend logs for more details."})

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

if __name__ == '__main__':
    uvicorn.run(app, host='0.0.0.0', port=8090)