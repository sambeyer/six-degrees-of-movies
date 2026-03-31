#!/bin/sh
set -e

DATA_DIR="${ACTOR_GAME_DATA_DIR:-/data}"
DB="$DATA_DIR/imdb.db"
GCS_BUCKET="${GCS_BUCKET:-}"

# Use the pre-built venv directly — avoids uv trying to re-sync at runtime
# (which would fail because the venv is owned by root, not the nonroot user).
PYTHON=/app/.venv/bin/python

mkdir -p "$DATA_DIR"

if [ -f "$DB" ]; then
    echo "==> Using local database at $DB"

elif [ -n "$GCS_BUCKET" ] && "$PYTHON" /app/gcs_db.py db-exists "$GCS_BUCKET"; then
    echo "==> Downloading database from gs://$GCS_BUCKET ..."
    "$PYTHON" /app/gcs_db.py download-db "$GCS_BUCKET" "$DB"
    echo "==> Database ready."

else
    echo "======================================================="
    echo "  No database found locally or in GCS."
    echo "  Running first-time setup (may take 15-30 minutes)."
    echo "  TIP: pre-seed GCS with the DB to avoid this on every"
    echo "  cold start:  gsutil cp ~/.actor-game/imdb.db gs://BUCKET/"
    echo "======================================================="

    # Pull any cached raw files from GCS first to avoid re-downloading
    # from IMDB (saves ~1.2 GB of bandwidth and several minutes)
    if [ -n "$GCS_BUCKET" ]; then
        echo "==> Syncing cached raw files from GCS (if available)..."
        "$PYTHON" /app/gcs_db.py sync-raw "$GCS_BUCKET" "$DATA_DIR"
    fi

    /app/.venv/bin/actor-game setup

    if [ -n "$GCS_BUCKET" ]; then
        echo "==> Uploading database and raw files to gs://$GCS_BUCKET ..."
        "$PYTHON" /app/gcs_db.py upload-all "$GCS_BUCKET" "$DATA_DIR"
        echo "==> Upload complete."
    fi
fi

echo "==> Starting server on 0.0.0.0:8080 ..."
exec /app/.venv/bin/uvicorn server:app --host 0.0.0.0 --port 8080
