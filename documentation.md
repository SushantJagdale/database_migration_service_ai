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
    uvicorn main:app --host 0.0.0.0 --port 8080
    ```
    The backend will be running at `http://localhost:8080`.

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
    BACKEND_URL="http://localhost:8080"
    ```
5.  **Run the frontend server:**
    ```bash
    uvicorn main:app --host 0.0.0.0 --port 8000
    ```
    The frontend will be accessible at `http://localhost:8000`.

## Deploying to Cloud Run

### Backend Deployment

1.  **Navigate to the backend directory:**
    ```bash
    cd backend
    ```
2.  **Build the Docker image:**
    ```bash
    gcloud builds submit --config cloudbuild.yaml .
    ```
3.  **Deploy to Cloud Run:**
    ```bash
    gcloud run deploy dms-backend \
        --image gcr.io/migration-demo-429608/dms-backend:latest \
        --platform managed \
        --region us-central1 \
        --allow-unauthenticated \
        --port 8080 \
        --set-secrets=GOOGLE_API_KEY=GOOGLE_API_KEY:latest \
        --set-env-vars="MODEL=gemini-1.5-flash,GCP_PROJECT_ID=migration-demo-429608,REGION=us-central1,AWS_ACCESS_KEY_ID=none,AWS_SECRET_ACCESS_KEY=none"
    ```

### Frontend Deployment

1.  **Navigate to the frontend directory:**
    ```bash
    cd frontend
    ```
2.  **Build the Docker image:**
    ```bash
    gcloud builds submit --config cloudbuild.yaml .
    ```
3.  **Deploy to Cloud Run:**
    ```bash
    gcloud run deploy dms-frontend \
        --image gcr.io/migration-demo-429608/dms-frontend:latest \
        --platform managed \
        --region us-central1 \
        --allow-unauthenticated \
        --set-env-vars="BACKEND_URL=https://dms-backend-214722091571.us-central1.run.app,PROJECT_ID=migration-demo-429608,REGION=us-central1"
    ```

