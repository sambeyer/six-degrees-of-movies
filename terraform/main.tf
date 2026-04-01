terraform {
  required_version = ">= 1.5"

  # Backend config is supplied via -backend-config=backend.tfvars (local) or
  # -backend-config flags (CI). See backend.tfvars.example.
  backend "gcs" {}

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

provider "cloudflare" {
  api_token = var.cloudflare_api_token
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

# ── Cloudflare Worker — reverse proxy to Cloud Run ────────────────────────────
# australia-southeast2 doesn't support Cloud Run domain mappings, so we use a
# Cloudflare Worker to proxy sixdegreesofmovies.com → the Cloud Run URL.
# The Worker is re-deployed on every `terraform apply`, keeping the Cloud Run
# URL in sync automatically after each image deploy.

locals {
  cloudrun_hostname = trimprefix(google_cloud_run_v2_service.app.uri, "https://")

  worker_script = <<-JS
    const UPSTREAM = "${local.cloudrun_hostname}";

    addEventListener('fetch', event => {
      event.respondWith(handleRequest(event.request));
    });

    async function handleRequest(request) {
      const url = new URL(request.url);
      url.hostname = UPSTREAM;
      url.protocol = 'https:';
      return fetch(new Request(url, request));
    }
  JS
}

resource "cloudflare_workers_script" "proxy" {
  account_id = var.cloudflare_account_id
  name       = "sixdegreesofmovies-proxy"
  content    = local.worker_script
}

resource "cloudflare_workers_route" "site" {
  zone_id     = var.cloudflare_zone_id
  pattern     = "${var.domain}/*"
  script_name = cloudflare_workers_script.proxy.name
}

# Dummy A record required for Cloudflare to proxy the domain.
# Traffic never reaches 192.0.2.1 — Cloudflare intercepts it via the Worker route.
resource "cloudflare_record" "root" {
  zone_id = var.cloudflare_zone_id
  name    = "@"
  content = "192.0.2.1"
  type    = "A"
  proxied = true
}

