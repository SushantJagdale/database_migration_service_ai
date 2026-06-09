# Terraform Deployment for Database Migration Service

This directory contains the Terraform configuration to deploy the frontend and backend services to Google Cloud Run.

## Architecture

- **dms-backend**: Cloud Run service running the FastAPI backend server. It interacts with the Gemini LLM and AWS RDS APIs.
- **dms-frontend**: Cloud Run service running the FastAPI/Jinja2 frontend, acting as a proxy to the backend.
- **Secret Manager**: A secret `GOOGLE_API_KEY` is created to securely store the API key required for Gemini LLM.
- **Service Accounts**: Separate service accounts are created for backend and frontend following the principle of least privilege.

---

## Deployment Steps

### 1. Build and Push Container Images

Before deploying via Terraform, you need to build and push the container images using Google Cloud Build. 

> **Note**: If deploying to a project other than `migration-demo-429608`, edit the image names in `backend/cloudbuild.yaml` and `frontend/cloudbuild.yaml` first.

1. **Build the Backend Image:**
   ```bash
   cd backend
   gcloud builds submit --config cloudbuild.yaml .
   ```

2. **Build the Frontend Image:**
   ```bash
   cd frontend
   gcloud builds submit --config cloudbuild.yaml .
   ```

---

### 2. Configure Terraform

1. Navigate to the `terraform` directory:
   ```bash
   cd terraform
   ```

2. Copy the example variables file:
   ```bash
   cp terraform.tfvars.example terraform.tfvars
   ```

3. Open `terraform.tfvars` and configure the following variables:
   - `project_id`: Your Google Cloud Project ID.
   - `region`: The GCP region to deploy to (default: `us-central1`).
   - `google_api_key`: (Optional but recommended) Your Google Gemini API Key. If provided, Terraform will write it to Secret Manager. If not provided, you must add it manually to Secret Manager later.

---

### 3. Deploy

1. Initialize Terraform (downloads providers and configures local backend):
   ```bash
   terraform init
   ```

2. Plan the deployment to verify resources:
   ```bash
   terraform plan
   ```

3. Deploy the infrastructure:
   ```bash
   terraform apply
   ```

4. Once applied, Terraform will output the URLs:
   - `frontend_url`: The public-facing web interface.
   - `backend_url`: The API endpoint.

---

## Clean Up

To tear down the deployed infrastructure, run:
```bash
terraform destroy
```
*(Note: Enabling/disabling APIs will not be undone to prevent breaking other services in the project).*
