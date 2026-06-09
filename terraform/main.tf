terraform {
  required_version = ">= 1.3.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

data "google_project" "project" {
  project_id = var.project_id
}


# --- APIs to enable ---

resource "google_project_service" "iam" {
  project            = var.project_id
  service            = "iam.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "run" {
  project            = var.project_id
  service            = "run.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "secretmanager" {
  project            = var.project_id
  service            = "secretmanager.googleapis.com"
  disable_on_destroy = false
}

# Override Org Policy constraint to allow public Cloud Run invocation (if enabled)
resource "google_project_organization_policy" "allow_all_domains" {
  count      = var.override_org_domain_restriction ? 1 : 0
  project    = var.project_id
  constraint = "constraints/iam.allowedPolicyMemberDomains"

  list_policy {
    allow {
      all = true
    }
  }
}


# --- Service Accounts ---

resource "google_service_account" "backend" {
  account_id   = "dms-backend-sa"
  display_name = "Database Migration Service Backend Service Account"
  project      = var.project_id
  depends_on   = [google_project_service.iam]
}

resource "google_service_account" "frontend" {
  account_id   = "dms-frontend-sa"
  display_name = "Database Migration Service Frontend Service Account"
  project      = var.project_id
  depends_on   = [google_project_service.iam]
}

# --- Secret Manager ---

data "google_secret_manager_secret" "google_api_key" {
  secret_id = var.google_api_key_secret_name
  project   = var.project_id
}

# Grant the backend service account access to read the secret
resource "google_secret_manager_secret_iam_member" "backend_secret_accessor" {
  project   = var.project_id
  secret_id = data.google_secret_manager_secret.google_api_key.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.backend.email}"
}

# --- Cloud Run: Backend Service ---

resource "google_cloud_run_v2_service" "backend" {
  name     = "dms-backend"
  location = var.region
  project  = var.project_id
  ingress  = "INGRESS_TRAFFIC_ALL"


  template {
    service_account = google_service_account.backend.email

    containers {
      image = var.backend_image
      ports {
        container_port = 8080
      }
      env {
        name  = "MODEL"
        value = var.model_name
      }
      env {
        name  = "GCP_PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "REGION"
        value = var.region
      }
      env {
        name  = "AWS_ACCESS_KEY_ID"
        value = "none"
      }
      env {
        name  = "AWS_SECRET_ACCESS_KEY"
        value = "none"
      }
      env {
        name = "GOOGLE_API_KEY"
        value_source {
          secret_key_ref {
            secret  = data.google_secret_manager_secret.google_api_key.secret_id
            version = "latest"
          }
        }
      }
    }
  }

  # Ensure IAM bindings are created before service deployment
  depends_on = [
    google_project_service.run,
    google_secret_manager_secret_iam_member.backend_secret_accessor
  ]
}

# Allow unauthenticated (public) access to Backend Service
resource "google_cloud_run_v2_service_iam_member" "backend_invoker" {
  count    = var.allow_unauthenticated ? 1 : 0
  project  = google_cloud_run_v2_service.backend.project
  location = google_cloud_run_v2_service.backend.location
  name     = google_cloud_run_v2_service.backend.name
  role     = "roles/run.invoker"
  member   = "allUsers"

  depends_on = [
    google_project_organization_policy.allow_all_domains
  ]
}

# --- Cloud Run: Frontend Service ---

resource "google_cloud_run_v2_service" "frontend" {
  name     = "dms-frontend"
  location = var.region
  project  = var.project_id
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.frontend.email

    containers {
      image = var.frontend_image
      ports {
        container_port = 8080
      }
      env {
        name  = "BACKEND_URL"
        value = "https://${google_cloud_run_v2_service.backend.name}-${data.google_project.project.number}.${var.region}.run.app"
      }
      env {
        name  = "PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "REGION"
        value = var.region
      }
    }
  }

  depends_on = [
    google_project_service.run,
    google_cloud_run_v2_service.backend
  ]
}

# Allow unauthenticated (public) access to Frontend Service
resource "google_cloud_run_v2_service_iam_member" "frontend_invoker" {
  count    = var.allow_unauthenticated ? 1 : 0
  project  = google_cloud_run_v2_service.frontend.project
  location = google_cloud_run_v2_service.frontend.location
  name     = google_cloud_run_v2_service.frontend.name
  role     = "roles/run.invoker"
  member   = "allUsers"

  depends_on = [
    google_project_organization_policy.allow_all_domains
  ]
}
