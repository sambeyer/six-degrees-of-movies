"""Container entrypoint — bootstraps the database then starts the API server."""

import os
import subprocess
import sys
from pathlib import Path

DATA_DIR = Path(os.environ.get("ACTOR_GAME_DATA_DIR", "/data"))
DB = DATA_DIR / "imdb.db"
GCS_BUCKET = os.environ.get("GCS_BUCKET", "")


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if DB.exists():
        print(f"==> Using local database at {DB}", flush=True)

    elif GCS_BUCKET:
        from gcs_db import db_exists, download_db
        if db_exists(GCS_BUCKET):
            print(f"==> Downloading database from gs://{GCS_BUCKET} ...", flush=True)
            download_db(GCS_BUCKET, str(DB))
            print("==> Database ready.", flush=True)
        else:
            _build_from_scratch()
    else:
        _build_from_scratch()

    print("==> Starting server on 0.0.0.0:8080 ...", flush=True)
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8080)


def _build_from_scratch() -> None:
    print("=======================================================", flush=True)
    print("  No database found locally or in GCS.", flush=True)
    print("  Running first-time setup (may take 15-30 minutes).", flush=True)
    print("  TIP: pre-seed GCS with the DB to avoid this on every", flush=True)
    print(f"  cold start:  gsutil cp ~/.actor-game/imdb.db gs://{GCS_BUCKET}/", flush=True)
    print("=======================================================", flush=True)

    if GCS_BUCKET:
        from gcs_db import sync_raw_from_gcs
        print("==> Syncing cached raw files from GCS (if available)...", flush=True)
        sync_raw_from_gcs(GCS_BUCKET, str(DATA_DIR))

    subprocess.run([sys.executable, "/app/src/actor_game.py", "setup"], check=True)

    if GCS_BUCKET:
        from gcs_db import upload_all
        print(f"==> Uploading database and raw files to gs://{GCS_BUCKET} ...", flush=True)
        upload_all(GCS_BUCKET, str(DATA_DIR))
        print("==> Upload complete.", flush=True)


if __name__ == "__main__":
    main()
