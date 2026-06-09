variable "project_id" {
  type        = string
  description = "The Google Cloud project ID to deploy to."
}

variable "region" {
  type        = string
  description = "The Google Cloud region to deploy the services to."
  default     = "us-central1"
}

variable "backend_image" {
  type        = string
  description = "The Docker image path for the backend service."
  default     = "gcr.io/migration-demo-429608/dms-backend:latest"
}

variable "frontend_image" {
  type        = string
  description = "The Docker image path for the frontend service."
  default     = "gcr.io/migration-demo-429608/dms-frontend:latest"
}

variable "model_name" {
  type        = string
  description = "The model name for Gemini LLM."
  default     = "gemini-2.5-flash"
}


variable "google_api_key_secret_name" {
  type        = string
  description = "The name of the Secret Manager secret for the GOOGLE_API_KEY."
  default     = "GOOGLE_API_KEY"
}

variable "google_api_key" {
  type        = string
  description = "The Google Gemini API Key value. If provided, Terraform will create a new version of the secret."
  sensitive   = true
  default     = ""
}

variable "allow_unauthenticated" {
  type        = bool
  description = "Whether to allow unauthenticated (public) access to the services. Set to false if GCP Org domain restrictions prevent public access."
  default     = false
}

variable "override_org_domain_restriction" {
  type        = bool
  description = "Whether to override the organization policy constraint iam.allowedPolicyMemberDomains on the project."
  default     = false
}


