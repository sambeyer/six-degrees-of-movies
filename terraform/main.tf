terraform {
  required_version = ">= 1.5"

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

# ── Enable required GCP APIs ──────────────────────────────────────────────────

resource "google_project_service" "apis" {
  for_each = toset([
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
    "storage.googleapis.com",
    "iam.googleapis.com",
  ])

  service            = each.key
  disable_on_destroy = false
}

# ── Artifact Registry — Docker image repository ───────────────────────────────

resource "google_artifact_registry_repository" "images" {
  location      = var.region
  repository_id = "actor-game"
  format        = "DOCKER"
  description   = "Docker images for Actor Connection Game"

  depends_on = [google_project_service.apis]
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

# Grant the Cloud Run SA read/write access to the data bucket
# (write is needed for the first-time setup path that uploads the built DB)
resource "google_storage_bucket_iam_member" "run_data" {
  bucket = google_storage_bucket.data.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.run.email}"
}

# ── Cloud Run service ─────────────────────────────────────────────────────────

resource "google_cloud_run_v2_service" "app" {
  name     = "actor-game"
  location = var.region

  template {
    service_account = google_service_account.run.email

    containers {
      image = var.image

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

  depends_on = [google_project_service.apis]
}

# Allow unauthenticated public access
resource "google_cloud_run_v2_service_iam_member" "public_invoker" {
  location = google_cloud_run_v2_service.app.location
  name     = google_cloud_run_v2_service.app.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
