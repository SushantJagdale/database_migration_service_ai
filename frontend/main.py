import os
import subprocess
import json
import logging
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import requests
from pydantic import BaseModel

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Helper to load .env file manually
def load_env_file(filepath=".env"):
    if os.path.exists(filepath):
        with open(filepath, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    val = val.strip().strip('"').strip("'")
                    os.environ[key.strip()] = val

# Load local .env if present (fallback for local development)
load_env_file()

# The URL of the backend service will be injected as an environment variable
BACKEND_URL = os.environ.get("BACKEND_URL")
PROJECT_ID = os.environ.get("PROJECT_ID", "migration-demo-429608")
REGION = os.environ.get("REGION", "us-central1")

class ConfigureRequest(BaseModel):
    aws_account_id: str
    aws_access_key_id: str
    aws_secret_access_key: str

class DiscoverRequest(BaseModel):
    prompt: str

class ConfigureDmsRequest(BaseModel):
    prompt: str

class ValidateRequest(BaseModel):
    instance_id: str
    engine: str

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse(name="index.html", request=request)

@app.post("/configure")
async def configure(payload: ConfigureRequest):
    aws_account_id = payload.aws_account_id
    aws_access_key_id = payload.aws_access_key_id
    aws_secret_access_key = payload.aws_secret_access_key

    if not aws_account_id or not aws_access_key_id or not aws_secret_access_key:
        raise HTTPException(status_code=400, detail="Missing AWS credentials or Account ID.")

    # try:
    #     # Format the environment variables for the update command
    #     env_vars_str = f"AWS_ACCESS_KEY_ID={aws_access_key_id},AWS_SECRET_ACCESS_KEY={aws_secret_access_key}"

    #     # Update the backend Cloud Run service with the new environment variables
    #     update_command = [
    #         "gcloud", "run", "services", "update", "dms-backend",
    #         "--platform", "managed",
    #         "--region", REGION,
    #         "--project", PROJECT_ID,
    #         f"--set-env-vars={env_vars_str}"
    #     ]
    #     update_result = subprocess.run(update_command, capture_output=True, text=True, check=True)
    #     return {"message": "AWS credentials configured successfully.", "details": update_result.stdout}
    # except subprocess.CalledProcessError as e:
    #     raise HTTPException(status_code=500, detail=f"Failed to update backend service: {e.stderr}")
    # except FileNotFoundError:
    #     raise HTTPException(status_code=500, detail="gcloud command not found. Make sure it's installed and in your PATH.")
    if not BACKEND_URL:
        raise HTTPException(status_code=500, detail="BACKEND_URL is not configured")

    try:
        payload_dict = payload.model_dump()
        logging.info(f"Forwarding to backend: {payload_dict}")
        response = requests.post(f"{BACKEND_URL}/configure", json=payload_dict)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Failed to connect to backend: {e}")


@app.post("/discover")
async def discover(payload: DiscoverRequest):
    if not BACKEND_URL:
        raise HTTPException(status_code=500, detail="BACKEND_URL is not configured")

    prompt = payload.prompt

    if not prompt:
        raise HTTPException(status_code=400, detail="Missing prompt")

    try:
        response = requests.post(f"{BACKEND_URL}/discover", json={"prompt": prompt})
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Failed to connect to backend: {e}")
    except requests.exceptions.JSONDecodeError:
        raise HTTPException(status_code=500, detail=f"Invalid JSON response from backend: {response.text}")

@app.post("/configuredms")
async def configure_dms(payload: ConfigureDmsRequest):
    if not BACKEND_URL:
        raise HTTPException(status_code=500, detail="BACKEND_URL is not configured")

    prompt = payload.prompt

    if not prompt:
        raise HTTPException(status_code=400, detail="Missing prompt")

    try:
        response = requests.post(f"{BACKEND_URL}/configuredms", json={"prompt": prompt})
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Failed to connect to backend: {e}")
    except requests.exceptions.JSONDecodeError:
        raise HTTPException(status_code=500, detail=f"Invalid JSON response from backend: {response.text}")

@app.post("/validate")
async def validate_proxy(payload: ValidateRequest):
    if not BACKEND_URL:
        raise HTTPException(status_code=500, detail="BACKEND_URL is not configured")

    try:
        response = requests.post(f"{BACKEND_URL}/validate", json=payload.model_dump())
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Failed to connect to backend: {e}")
    except requests.exceptions.JSONDecodeError:
        raise HTTPException(status_code=500, detail=f"Invalid JSON response from backend: {response.text}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8082)