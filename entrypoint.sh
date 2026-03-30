#!/bin/sh
set -e

DATA_DIR="${ACTOR_GAME_DATA_DIR:-/data}"
DB="$DATA_DIR/imdb.db"

# Ensure the data directory exists (the volume mount may be an empty dir)
mkdir -p "$DATA_DIR"

if [ ! -f "$DB" ]; then
    echo "======================================================="
    echo "  No database found at $DB"
    echo "  Running first-time setup — downloading IMDB data."
    echo "  This will fetch ~1 GB and may take several minutes."
    echo "======================================================="
    uv run actor-game setup
    echo "==> Setup complete."
fi

echo "==> Starting web server on 0.0.0.0:8000 ..."
exec uv run uvicorn server:app --host 0.0.0.0 --port 8000
