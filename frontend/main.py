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
templates_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
templates = Jinja2Templates(directory=templates_dir)

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
load_env_file(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

# The URL of the backend service will be injected as an environment variable
BACKEND_URL = os.environ.get("BACKEND_URL")
PROJECT_ID = os.environ.get("PROJECT_ID", "migration-demo-429608")
REGION = os.environ.get("REGION", "asia-south1")

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

class DmsStatusRequest(BaseModel):
    job_name: str
    region: str


@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse(name="index.html", request=request)

def forward_post_request(endpoint: str, json_data: dict) -> dict:
    if not BACKEND_URL:
        raise HTTPException(status_code=500, detail="BACKEND_URL is not configured")
    try:
        response = requests.post(f"{BACKEND_URL}{endpoint}", json=json_data)
        if response.status_code >= 400:
            try:
                error_detail = response.json().get("detail", "Backend request failed.")
            except Exception:
                error_detail = response.text or "Backend request failed."
            raise HTTPException(status_code=response.status_code, detail=error_detail)
        return response.json()
    except requests.exceptions.RequestException as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"Failed to connect to backend: {e}")
    except requests.exceptions.JSONDecodeError:
        raise HTTPException(status_code=500, detail=f"Invalid JSON response from backend: {response.text}")

def forward_get_request(endpoint: str) -> dict:
    if not BACKEND_URL:
        raise HTTPException(status_code=500, detail="BACKEND_URL is not configured")
    try:
        response = requests.get(f"{BACKEND_URL}{endpoint}")
        if response.status_code >= 400:
            try:
                error_detail = response.json().get("detail", "Backend request failed.")
            except Exception:
                error_detail = response.text or "Backend request failed."
            raise HTTPException(status_code=response.status_code, detail=error_detail)
        return response.json()
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Failed to connect to backend: {e}")

@app.post("/configure")
async def configure(payload: ConfigureRequest):
    aws_account_id = payload.aws_account_id
    aws_access_key_id = payload.aws_access_key_id
    aws_secret_access_key = payload.aws_secret_access_key

    if not aws_account_id or not aws_access_key_id or not aws_secret_access_key:
        raise HTTPException(status_code=400, detail="Missing AWS credentials or Account ID.")

    return forward_post_request("/configure", payload.model_dump())

@app.post("/discover")
async def discover(payload: DiscoverRequest):
    prompt = payload.prompt
    if not prompt:
        raise HTTPException(status_code=400, detail="Missing prompt")
    return forward_post_request("/discover", {"prompt": prompt})

@app.post("/configuredms")
async def configure_dms(payload: ConfigureDmsRequest):
    prompt = payload.prompt
    if not prompt:
        raise HTTPException(status_code=400, detail="Missing prompt")
    return forward_post_request("/configuredms", {"prompt": prompt})

@app.post("/validate")
async def validate_proxy(payload: ValidateRequest):
    return forward_post_request("/validate", payload.model_dump())

@app.post("/dms/status")
async def dms_status_proxy(payload: DmsStatusRequest):
    return forward_post_request("/dms/status", payload.model_dump())

@app.get("/gcp-topology")
async def gcp_topology_proxy():
    return forward_get_request("/gcp-topology")

@app.get("/vpcs")
async def vpcs_proxy():
    return forward_get_request("/vpcs")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8081)