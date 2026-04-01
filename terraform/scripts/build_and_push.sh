#!/usr/bin/env bash
# Called by Terraform's external data source during `terraform plan`.
# Builds and pushes the Docker image when running on a local developer machine.
# In CI (any GITHUB_* env var is set) the build is skipped — CI is responsible
# for building and pushing before Terraform runs, and must set IMAGE_DIGEST.
#
# The image is always deployed by digest, never by tag, so no tag is written
# to the registry. A random temporary tag is used as a push handle then ignored.
#
# Input (JSON via stdin, from Terraform's external data source query):
#   { "project_id": "...", "region": "..." }
#
# Output (JSON to stdout):
#   { "image": "<registry>/<repo>@sha256:<digest>" }

set -euo pipefail

# Parse query from Terraform
eval "$(jq -r '@sh "PROJECT_ID=\(.project_id) REGION=\(.region)"')"

REGISTRY="${REGION}-docker.pkg.dev/${PROJECT_ID}/actor-game/actor-game"

# In CI, the image was already pushed by the workflow.
# The digest is passed via the IMAGE_DIGEST environment variable.
if printenv | grep -q '^GITHUB_'; then
  : "${IMAGE_DIGEST:?IMAGE_DIGEST env var must be set in CI (e.g. sha256:abc123...)}"
  jq -n --arg image "${REGISTRY}@${IMAGE_DIGEST}" '{"image": $image}'
  exit 0
fi

# Repo root is two levels up from this script (terraform/scripts/ → repo root)
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

# Configure Docker credentials for Artifact Registry
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet >&2

# Use a random temporary tag as a push handle — we deploy by digest, not tag.
TEMP_TAG="${REGISTRY}:tmp-$(python3 -c 'import uuid; print(uuid.uuid4().hex[:12])')"

# Build for linux/amd64 — required; Cloud Run is amd64, dev machines may be arm64
echo "==> Building image" >&2
docker build --platform linux/amd64 -t "$TEMP_TAG" "$REPO_ROOT" >&2

# Push and resolve the digest
echo "==> Pushing image" >&2
docker push "$TEMP_TAG" >&2

# RepoDigests holds the registry-assigned digest after a push
IMAGE_WITH_DIGEST=$(docker inspect --format='{{index .RepoDigests 0}}' "$TEMP_TAG")
echo "==> Digest: ${IMAGE_WITH_DIGEST}" >&2

jq -n --arg image "$IMAGE_WITH_DIGEST" '{"image": $image}'
