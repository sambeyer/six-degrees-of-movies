output "service_url" {
  description = "Public URL of the Cloud Run service"
  value       = google_cloud_run_v2_service.app.uri
}

output "data_bucket" {
  description = "GCS bucket name — upload imdb.db here to pre-seed Cloud Run"
  value       = google_storage_bucket.data.name
}

output "artifact_registry_repo" {
  description = "Docker repository path (use as the image prefix when pushing)"
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/actor-game/actor-game"
}

output "deploy_commands" {
  description = "Commands to build, push, and redeploy after a code change"
  value       = <<-EOT
    # Authenticate Docker with Artifact Registry (once):
    gcloud auth configure-docker ${var.region}-docker.pkg.dev

    # Build and push:
    docker build -t ${var.region}-docker.pkg.dev/${var.project_id}/actor-game/actor-game:latest .
    docker push ${var.region}-docker.pkg.dev/${var.project_id}/actor-game/actor-game:latest

    # Redeploy via Terraform:
    terraform apply -var="image=${var.region}-docker.pkg.dev/${var.project_id}/actor-game/actor-game:latest"

    # Pre-seed the DB so Cloud Run doesn't rebuild from scratch on first cold start:
    gsutil cp ~/.actor-game/imdb.db gs://${google_storage_bucket.data.name}/
  EOT
}
