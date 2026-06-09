output "backend_url" {
  value       = "https://${google_cloud_run_v2_service.backend.name}-${data.google_project.project.number}.${var.region}.run.app"
  description = "The URL of the backend Cloud Run service."
}

output "frontend_url" {
  value       = "https://${google_cloud_run_v2_service.frontend.name}-${data.google_project.project.number}.${var.region}.run.app"
  description = "The URL of the frontend Cloud Run service."
}


