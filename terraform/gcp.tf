# ── Docker image — build locally, skip in CI ─────────────────────────────────
# Runs build_and_push.sh during `terraform plan`. On a developer laptop it
# builds and pushes the image; in CI (any GITHUB_* env var present) it skips
# the build and returns the pre-pushed image URI (passed via IMAGE_DIGEST env).
# The image is always referenced by digest, never by tag.

data "external" "docker_image" {
  program = ["${path.module}/scripts/build_and_push.sh"]

  query = {
    project_id = var.project_id
    region     = var.region
  }
}

# ── Artifact Registry — Docker image repository ───────────────────────────────

resource "google_artifact_registry_repository" "images" {
  location      = var.region
  repository_id = "actor-game"
  format        = "DOCKER"
  description   = "Docker images for Actor Connection Game"

  docker_config {
    immutable_tags = true
  }
}

# ── GCS bucket — IMDB data storage ───────────────────────────────────────────
# Stores the processed imdb.db (~850 MB) and the raw IMDB TSV files.
# Cloud Run instances download imdb.db on cold start (~30–60 s).

resource "google_storage_bucket" "data" {
  name                        = "${var.project_id}-actor-game-data"
  location                    = var.region
  uniform_bucket_level_access = true

  # Prevent accidental deletion of the database
  force_destroy = false
}

# ── Cloud Run service account ─────────────────────────────────────────────────

resource "google_service_account" "run" {
  account_id   = "actor-game-run"
  display_name = "Actor Game — Cloud Run runtime SA"
}

data "google_client_openid_userinfo" "current" {}

# Allow the currently-authenticated identity (Terraform SA) to attach the
# Cloud Run SA to Cloud Run services.
resource "google_service_account_iam_member" "terraform_uses_run_sa" {
  service_account_id = google_service_account.run.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${data.google_client_openid_userinfo.current.email}"
}

# Grant the Cloud Run SA read/write access to the data bucket
# (write is needed for the first-time setup path that uploads the built DB)
resource "google_storage_bucket_iam_member" "run_data" {
  bucket = google_storage_bucket.data.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.run.email}"
}

# ── Cloud Run service ─────────────────────────────────────────────────────────

resource "google_cloud_run_v2_service" "app" {
  name       = "actor-game"
  location   = var.region
  depends_on = [google_service_account_iam_member.terraform_uses_run_sa]

  template {
    service_account = google_service_account.run.email

    containers {
      image = data.external.docker_image.result.image

      ports {
        container_port = 8080
      }

      env {
        name  = "ACTOR_GAME_DATA_DIR"
        value = "/tmp/actor-game"
      }

      env {
        name  = "GCS_BUCKET"
        value = google_storage_bucket.data.name
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "2Gi"
        }
        cpu_idle = true
      }

      # Allow enough time for the DB to download from GCS on cold start.
      # 850 MB at typical GCS speeds takes ~30–60 s; we allow 10 minutes
      # as a safety margin (also covers the rare from-scratch setup path).
      startup_probe {
        http_get {
          path = "/api/info"
        }
        initial_delay_seconds = 5
        period_seconds        = 10
        timeout_seconds       = 5
        failure_threshold     = 60 # 10 minutes max
      }
    }

    scaling {
      min_instance_count = 0
      max_instance_count = var.max_instances
    }
  }
}

# Allow unauthenticated public access
resource "google_cloud_run_v2_service_iam_member" "public_invoker" {
  location = google_cloud_run_v2_service.app.location
  name     = google_cloud_run_v2_service.app.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
