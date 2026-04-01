#!/usr/bin/env bash
# Sets up GitHub Actions secrets and variables for the Six Degrees of Movies deploy workflow.
#
# Prerequisites:
#   - gh CLI installed and authenticated (gh auth login)
#   - gcloud CLI installed and authenticated with permission to create SA keys
#
# Usage:
#   ./scripts/setup-github-secrets.sh

set -euo pipefail

# ── Helpers ────────────────────────────────────────────────────────────────────

prompt() {
  local var_name="$1"
  local prompt_text="$2"
  local default="${3:-}"

  if [[ -n "$default" ]]; then
    read -rp "$prompt_text [$default]: " value
    echo "${value:-$default}"
  else
    read -rp "$prompt_text: " value
    echo "$value"
  fi
}

prompt_secret() {
  local prompt_text="$1"
  read -rsp "$prompt_text: " value
  echo ""  # newline after hidden input
  echo "$value"
}

# ── Detect repo ────────────────────────────────────────────────────────────────

REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null || true)
if [[ -z "$REPO" ]]; then
  REPO=$(prompt "REPO" "GitHub repo (owner/name)")
fi
echo "Using repo: $REPO"
echo ""

# ── GCP SA key ─────────────────────────────────────────────────────────────────

echo "=== GCP Service Account Key ==="
GCP_PROJECT_ID=$(prompt "GCP_PROJECT_ID" "GCP project ID")
SA_EMAIL=$(prompt "SA_EMAIL" "Terraform service account email")

KEY_FILE=$(mktemp /tmp/sa-key-XXXXXX.json)
trap 'rm -f "$KEY_FILE"' EXIT

echo "Creating new SA key for $SA_EMAIL..."
gcloud iam service-accounts keys create "$KEY_FILE" \
  --iam-account="$SA_EMAIL" \
  --project="$GCP_PROJECT_ID"

echo "Storing GCP_SA_KEY secret..."
gh secret set GCP_SA_KEY --repo="$REPO" < "$KEY_FILE"
echo "  ✓ GCP_SA_KEY"
echo ""

# ── Cloudflare secrets ─────────────────────────────────────────────────────────

echo "=== Cloudflare ==="
echo "(Find these in the Cloudflare dashboard)"
echo ""

CF_API_TOKEN=$(prompt_secret "Cloudflare API token (My Profile → API Tokens)")
gh secret set CLOUDFLARE_API_TOKEN --repo="$REPO" --body="$CF_API_TOKEN"
echo "  ✓ CLOUDFLARE_API_TOKEN"

CF_ACCOUNT_ID=$(prompt "CF_ACCOUNT_ID" "Cloudflare account ID (domain Overview → right sidebar)")
CF_ZONE_ID=$(prompt "CF_ZONE_ID" "Cloudflare zone ID (domain Overview → right sidebar)")
echo ""

# ── GitHub Variables (non-sensitive config) ────────────────────────────────────

echo "=== GitHub Variables ==="
GCS_BUCKET=$(prompt "GCS_BUCKET" "GCS data bucket name" "six-degrees-imdb-actor-game-data")

gh variable set GCP_PROJECT_ID  --repo="$REPO" --body="$GCP_PROJECT_ID"
gh variable set GCS_BUCKET      --repo="$REPO" --body="$GCS_BUCKET"
gh variable set CLOUDFLARE_ACCOUNT_ID --repo="$REPO" --body="$CF_ACCOUNT_ID"
gh variable set CLOUDFLARE_ZONE_ID    --repo="$REPO" --body="$CF_ZONE_ID"

echo "  ✓ GCP_PROJECT_ID"
echo "  ✓ GCS_BUCKET"
echo "  ✓ CLOUDFLARE_ACCOUNT_ID"
echo "  ✓ CLOUDFLARE_ZONE_ID"
echo ""

echo "All done. Run the workflow with: gh workflow run ci.yml --repo=$REPO"
