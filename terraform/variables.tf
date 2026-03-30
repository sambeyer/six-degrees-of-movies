variable "project_id" {
  description = "GCP project ID (e.g. my-project-123)"
  type        = string
}

variable "region" {
  description = "GCP region for all resources"
  type        = string
  default     = "us-central1"
}

variable "image" {
  description = <<-EOT
    Full Docker image URI to deploy, e.g.:
      us-central1-docker.pkg.dev/PROJECT/actor-game/actor-game:latest

    On first apply (before the image has been built and pushed), leave this
    as the default placeholder — it creates a functioning Cloud Run service
    that serves a Hello World page. Re-apply with the real image URI once
    you've pushed the image to Artifact Registry.
  EOT
  type        = string
  default     = "us-docker.pkg.dev/cloudrun/container/hello"
}

variable "max_instances" {
  description = "Maximum number of Cloud Run instances (controls cost ceiling)"
  type        = number
  default     = 3
}
