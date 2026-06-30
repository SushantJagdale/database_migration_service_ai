# Deployment Documentation

This document provides the necessary commands and image details for deploying the frontend and backend services.

## Running the Application Locally

### Prerequisites
- Python 3.9+
- pip
- Google Cloud SDK (`gcloud`)

### Backend Setup

1.  **Navigate to the backend directory:**
    ```bash
    cd backend
    ```
2.  **Create and activate a virtual environment:**
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    ```
3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
4.  **Set environment variables:**
    Create a `.env` file in the `backend` directory with the following content:
    ```
    GOOGLE_API_KEY="your-google-api-key"
    ```
5.  **Run the backend server:**
    ```bash
    python main.py
    ```
    The backend will be running at `http://localhost:8090`.

### Frontend Setup

1.  **Navigate to the frontend directory:**
    ```bash
    cd frontend
    ```
2.  **Create and activate a virtual environment:**
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    ```
3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
4.  **Set environment variables:**
    Create a `.env` file in the `frontend` directory with the following content:
    ```
    BACKEND_URL="http://localhost:8090"
    ```
5.  **Run the frontend server:**
    ```bash
    python main.py
    ```
    The frontend will be accessible at `http://localhost:8080`.

## Secret Manager Setup for DMS Migration

The DMS Migration Agent retrieves source database credentials dynamically from Google Cloud Secret Manager to configure the connection profiles.

Before running the application or triggering DMS configuration, ensure you have created the following secrets in your GCP project:

1.  **Username Secret:**
    *   **Secret Name:** `{source_db_instance_id}_user` (e.g. `gemini-mysql-instance-1_user`)
    *   **Secret Value:** The database master username (e.g. `admin`).
2.  **Password Secret:**
    *   **Secret Name:** `{source_db_instance_id}_password` (e.g. `gemini-mysql-instance-1_password`)
    *   **Secret Value:** The database password.

### GCP Permissions
Ensure the service account running the backend application (or your active `gcloud` context if running locally) has the **Secret Manager Secret Accessor** (`roles/secretmanager.secretAccessor`) role granted on these secrets.

## Deploying to Cloud Run

### Backend Deployment

1.  **Navigate to the backend directory:**
    ```bash
    cd backend
    ```
2.  **Build the Docker image:**
    Ensure you have configured your active project using `gcloud config set project <YOUR_PROJECT_ID>`, then build the image:
    ```bash
    gcloud builds submit --config cloudbuild.yaml .
    ```
3.  **Deploy to Cloud Run:**
    Deploy the backend service and capture the **Service URL** generated in the output (e.g. `https://dms-backend-xxxxx.a.run.app`):
    ```bash
    gcloud run deploy dms-backend \
        --image gcr.io/<YOUR_PROJECT_ID>/dms-backend:latest \
        --platform managed \
        --region us-central1 \
        --allow-unauthenticated \
        --port 8080 \
        --set-secrets=GOOGLE_API_KEY=GOOGLE_API_KEY:latest \
        --set-env-vars="MODEL=gemini-2.5-flash,GCP_PROJECT_ID=<YOUR_PROJECT_ID>,REGION=us-central1,AWS_ACCESS_KEY_ID=none,AWS_SECRET_ACCESS_KEY=none"
    ```

### Frontend Deployment

1.  **Navigate to the frontend directory:**
    ```bash
    cd frontend
    ```
2.  **Build the Docker image:**
    Ensure the active project is set, then build the image:
    ```bash
    gcloud builds submit --config cloudbuild.yaml .
    ```
3.  **Deploy to Cloud Run:**
    Deploy the frontend service, passing the backend service URL captured from Step 3 of the Backend Deployment as the `BACKEND_URL` environment variable:
    ```bash
    gcloud run deploy dms-frontend \
        --image gcr.io/<YOUR_PROJECT_ID>/dms-frontend:latest \
        --platform managed \
        --region us-central1 \
        --allow-unauthenticated \
        --set-env-vars="BACKEND_URL=<YOUR_BACKEND_SERVICE_URL>,PROJECT_ID=<YOUR_PROJECT_ID>,REGION=us-central1"
    ```

