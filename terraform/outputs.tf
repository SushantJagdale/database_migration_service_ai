output "backend_url" {
  value       = "https://${google_cloud_run_v2_service.backend.name}-${data.google_project.project.number}.${var.region}.run.app"
  description = "The URL of the backend Cloud Run service."
}

output "frontend_url" {
  value       = "https://${google_cloud_run_v2_service.frontend.name}-${data.google_project.project.number}.${var.region}.run.app"
  description = "The URL of the frontend Cloud Run service."
}

output "frontend_image_url" {
  value       = data.google_container_registry_image.frontend.image_url
  description = "The resolved image URL with digest of the frontend image."
}

output "backend_image_url" {
  value       = data.google_container_registry_image.backend.image_url
  description = "The resolved image URL with digest of the backend image."
}
