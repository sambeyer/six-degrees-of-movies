#!/usr/bin/env python3
"""
GCS helper — manages IMDB data files in Cloud Storage.

Usage (called by entrypoint.sh):
  python gcs_db.py db-exists   BUCKET
  python gcs_db.py download-db BUCKET LOCAL_PATH
  python gcs_db.py sync-raw    BUCKET DATA_DIR
  python gcs_db.py upload-all  BUCKET DATA_DIR
"""

import sys
from pathlib import Path

# Raw IMDB data files (cached in GCS to avoid re-downloading from IMDB)
RAW_FILES = [
    "name.basics.tsv.gz",
    "title.basics.tsv.gz",
    "title.principals.tsv.gz",
    "title.ratings.tsv.gz",
]


def _bucket(bucket_name: str):
    from google.cloud import storage
    return storage.Client().bucket(bucket_name)


def db_exists(bucket_name: str) -> bool:
    return _bucket(bucket_name).blob("imdb.db").exists()


def download_db(bucket_name: str, local_path: str) -> None:
    blob = _bucket(bucket_name).blob("imdb.db")
    blob.reload()
    size_mb = (blob.size or 0) / 1e6
    print(f"  imdb.db ({size_mb:.0f} MB)...", flush=True)
    blob.download_to_filename(local_path)
    print("  Done.", flush=True)


def sync_raw_from_gcs(bucket_name: str, data_dir: str) -> None:
    """Download any raw TSV files present in GCS that are missing locally."""
    bucket = _bucket(bucket_name)
    for filename in RAW_FILES:
        local = Path(data_dir) / filename
        if local.exists():
            continue
        blob = bucket.blob(filename)
        if blob.exists():
            print(f"  Downloading {filename} from GCS...", flush=True)
            blob.download_to_filename(str(local))


def upload_all(bucket_name: str, data_dir: str) -> None:
    """Upload the processed DB and all raw data files to GCS."""
    bucket = _bucket(bucket_name)
    for filename in ["imdb.db"] + RAW_FILES:
        local = Path(data_dir) / filename
        if not local.exists():
            continue
        print(f"  Uploading {filename}...", flush=True)
        bucket.blob(filename).upload_from_filename(str(local))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: gcs_db.py <cmd> <bucket> [path]", file=sys.stderr)
        sys.exit(1)

    cmd, bucket_arg = sys.argv[1], sys.argv[2]
    path_arg = sys.argv[3] if len(sys.argv) > 3 else None

    if cmd == "db-exists":
        sys.exit(0 if db_exists(bucket_arg) else 1)
    elif cmd == "download-db":
        download_db(bucket_arg, path_arg)
    elif cmd == "sync-raw":
        sync_raw_from_gcs(bucket_arg, path_arg)
    elif cmd == "upload-all":
        upload_all(bucket_arg, path_arg)
    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        sys.exit(1)
