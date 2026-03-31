#!/usr/bin/env bash
# Called by Terraform's external data source during `terraform plan`.
# Builds and pushes the Docker image when running on a local developer machine.
# In CI (any GITHUB_* env var is set) the build is skipped — CI is responsible
# for building and pushing before Terraform runs.
#
# Input (JSON via stdin, from Terraform's external data source query):
#   { "project_id": "...", "region": "...", "tag": "..." }
#
# Output (JSON to stdout):
#   { "image": "<full image URI>" }

set -euo pipefail

# Parse query from Terraform
eval "$(jq -r '@sh "PROJECT_ID=\(.project_id) REGION=\(.region) TAG=\(.tag)"')"

REGISTRY="${REGION}-docker.pkg.dev/${PROJECT_ID}/actor-game/actor-game"
IMAGE="${REGISTRY}:${TAG}"

# In CI, skip the build and just return the image URI.
if printenv | grep -q '^GITHUB_'; then
  jq -n --arg image "$IMAGE" '{"image": $image}'
  exit 0
fi

# Repo root is two levels up from this script (terraform/scripts/ → repo root)
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

# Configure Docker credentials for Artifact Registry
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet >&2

# Build for linux/amd64 — required; Cloud Run is amd64, dev machines may be arm64
echo "==> Building image: ${IMAGE}" >&2
docker build --platform linux/amd64 -t "$IMAGE" "$REPO_ROOT" >&2

# Push to Artifact Registry
echo "==> Pushing image: ${IMAGE}" >&2
docker push "$IMAGE" >&2

jq -n --arg image "$IMAGE" '{"image": $image}'
