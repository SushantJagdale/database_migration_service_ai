# The Google Cloud project ID to deploy to.
project_id = "migration-demo-429608"

# The Google Cloud region to deploy the services to.
region = "asia-south1"

# The Docker image path for the backend service.
backend_image = "gcr.io/migration-demo-429608/dms-backend:latest"

# The Docker image path for the frontend service.
frontend_image = "gcr.io/migration-demo-429608/dms-frontend:latest"

# The Google Gemini API Key. If provided, Terraform will create a new version of the secret.
google_api_key = "AIzaSyAUgqvIlY1sDWx3Jko-HXTt4S1PGVc1nOM"

# Allow public unauthenticated access to the Cloud Run services
allow_unauthenticated = true

# Disable the Org Policy domain restriction for this project to allow public access
override_org_domain_restriction = true
# VPC configurations for private database connectivity from Cloud Run
vpc_network    = "gc-vpc"
vpc_subnetwork = "subnet-asia1"
