# Frontend Development Plan for AWS RDS Pre-Migration Data Collector

## Objective

The goal is to create a simple, containerized web frontend to configure AWS credentials for the backend service. This frontend will be deployed as a Cloud Run service.

## Core Functionality

1.  **User Interface (UI):**
    -   A single web page with a form to accept:
        -   AWS Account ID
        -   AWS Access Key ID
        -   AWS Secret Access Key
    -   A "Configure AWS" button to submit the credentials.

2.  **Backend Logic:**
    -   A web server (Flask) will receive the credentials from the UI.
    -   Upon submission, the server will:
        1.  Execute `aws configure` commands to set the provided access key and secret key in the local environment. A default region (`us-east-1`) will be used.
        2.  Execute the `aws sts get-caller-identity` command to verify that the credentials have been configured correctly.
        3.  Display the output of the `aws sts get-caller-identity` command to the user on the web page.

## Technical Stack

-   **Framework:** Flask (a lightweight Python web framework)
-   **Containerization:** Docker
-   **Deployment:** Google Cloud Run

## File Structure

The `frontend` directory will be organized as follows:

```
frontend/
├── main.py             # The main Flask application file.
├── requirements.txt    # Python dependencies (Flask).
├── Dockerfile          # Dockerfile for building the container image.
├── PLAN.md             # This file.
└── templates/
    └── index.html      # The HTML template for the UI.
```

## Development Steps

1.  **Create `PLAN.md`:** Document the development plan (this file).
2.  **Create `requirements.txt`:** Add `Flask` as a dependency.
3.  **Create `templates/index.html`:** Build the HTML form for credential input.
4.  **Create `main.py`:**
    -   Set up a basic Flask application.
    -   Create a route `/` to render the `index.html` template.
    -   Create a route `/configure` (POST) to handle the form submission, run the AWS CLI commands, and return the result.
5.  **Create `Dockerfile`:**
    -   Start with a Python base image.
    -   Install the AWS CLI.
    -   Install the Python dependencies from `requirements.txt`.
    -   Copy the application files into the container.
    -   Set the `CMD` to run the Flask application.

## Deployment Instructions

1.  **Build the container image:**
    ```bash
    gcloud builds submit --tag gcr.io/migration-demo-429608/dms-frontend --project migration-demo-429608
    ```

2.  **Deploy to Cloud Run:**
    ```bash
    gcloud run deploy dms-frontend \
      --image gcr.io/migration-demo-429608/dms-frontend \
      --platform managed \
      --region us-central1 \
      --project=migration-demo-429608 \
      --allow-unauthenticated
    ```
3. **Set IAM Policy Binding**
   ```bash
   gcloud beta run services add-iam-policy-binding dms-frontend \
   --region=us-central1 \
   --member=allUsers \
   --role=roles/run.invoker \
   --project=migration-demo-429608
   ```