# Deployment Documentation

This document provides the necessary commands and image details for deploying the frontend and backend services.

## Backend

**Docker Image:**
`gcr.io/migration-demo-429608/dms-backend:latest`

**Deployment Command:**
```bash
gcloud run deploy dms-backend --image gcr.io/migration-demo-429608/dms-backend:latest --platform managed --region us-central1 --allow-unauthenticated --set-env-vars="MODEL=gemini-1.5-flash,PROJECT_ID=migration-demo-429608,REGION=us-central1,AWS_ACCESS_KEY_ID=none,AWS_SECRET_ACCESS_KEY=none"
```

## Frontend

**Docker Image:**
`gcr.io/migration-demo-429608/dms-frontend:latest`

**Deployment Command:**
```bash
gcloud run deploy dms-frontend --image gcr.io/migration-demo-429608/dms-frontend:latest --platform managed --region us-central1 --allow-unauthenticated --set-env-vars="BACKEND_URL=https://dms-backend-214722091571.us-central1.run.app,PROJECT_ID=migration-demo-429608,REGION=us-central1"
```
