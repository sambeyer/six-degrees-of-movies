"""Tests for container startup logic (entrypoint.py)."""

from pathlib import Path
from unittest.mock import call, patch

import pytest

import entrypoint as ep


@pytest.fixture(autouse=True)
def prevent_real_uvicorn():
    """Always patch uvicorn.run so no real server starts."""
    with patch("uvicorn.run") as mock:
        yield mock


class TestMain:
    def test_uses_local_db_when_present(self, tmp_path, monkeypatch, prevent_real_uvicorn):
        db = tmp_path / "imdb.db"
        db.touch()
        monkeypatch.setattr(ep, "DB", db)
        monkeypatch.setattr(ep, "DATA_DIR", tmp_path)
        monkeypatch.setattr(ep, "GCS_BUCKET", "")

        with patch("gcs_db.db_exists") as mock_exists:
            ep.main()

        mock_exists.assert_not_called()
        prevent_real_uvicorn.assert_called_once_with(
            "server:app", host="0.0.0.0", port=8080
        )

    def test_downloads_from_gcs_when_db_in_bucket(self, tmp_path, monkeypatch, prevent_real_uvicorn):
        db = tmp_path / "imdb.db"
        monkeypatch.setattr(ep, "DB", db)
        monkeypatch.setattr(ep, "DATA_DIR", tmp_path)
        monkeypatch.setattr(ep, "GCS_BUCKET", "my-bucket")

        with patch("gcs_db.db_exists", return_value=True) as mock_exists, \
             patch("gcs_db.download_db") as mock_dl:
            ep.main()

        mock_exists.assert_called_once_with("my-bucket")
        mock_dl.assert_called_once_with("my-bucket", str(db))
        prevent_real_uvicorn.assert_called_once()

    def test_builds_from_scratch_when_gcs_has_no_db(self, tmp_path, monkeypatch, prevent_real_uvicorn):
        db = tmp_path / "imdb.db"
        monkeypatch.setattr(ep, "DB", db)
        monkeypatch.setattr(ep, "DATA_DIR", tmp_path)
        monkeypatch.setattr(ep, "GCS_BUCKET", "my-bucket")

        with patch("gcs_db.db_exists", return_value=False), \
             patch("gcs_db.sync_raw_from_gcs") as mock_sync, \
             patch("gcs_db.upload_all") as mock_upload, \
             patch("subprocess.run") as mock_sub:
            ep.main()

        mock_sync.assert_called_once()
        mock_sub.assert_called_once()
        mock_upload.assert_called_once()

    def test_builds_from_scratch_without_gcs_bucket(self, tmp_path, monkeypatch, prevent_real_uvicorn):
        db = tmp_path / "imdb.db"
        monkeypatch.setattr(ep, "DB", db)
        monkeypatch.setattr(ep, "DATA_DIR", tmp_path)
        monkeypatch.setattr(ep, "GCS_BUCKET", "")

        with patch("gcs_db.sync_raw_from_gcs") as mock_sync, \
             patch("gcs_db.upload_all") as mock_upload, \
             patch("subprocess.run") as mock_sub:
            ep.main()

        mock_sync.assert_not_called()
        mock_upload.assert_not_called()
        mock_sub.assert_called_once()


class TestBuildFromScratch:
    def test_with_gcs_syncs_and_uploads(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ep, "DATA_DIR", tmp_path)
        monkeypatch.setattr(ep, "GCS_BUCKET", "my-bucket")

        with patch("gcs_db.sync_raw_from_gcs") as mock_sync, \
             patch("gcs_db.upload_all") as mock_upload, \
             patch("subprocess.run") as mock_sub:
            ep._build_from_scratch()

        mock_sync.assert_called_once_with("my-bucket", str(tmp_path))
        mock_sub.assert_called_once()
        mock_upload.assert_called_once_with("my-bucket", str(tmp_path))

    def test_without_gcs_only_runs_setup(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ep, "DATA_DIR", tmp_path)
        monkeypatch.setattr(ep, "GCS_BUCKET", "")

        with patch("gcs_db.sync_raw_from_gcs") as mock_sync, \
             patch("gcs_db.upload_all") as mock_upload, \
             patch("subprocess.run") as mock_sub:
            ep._build_from_scratch()

        mock_sync.assert_not_called()
        mock_upload.assert_not_called()
        mock_sub.assert_called_once()

    def test_setup_subprocess_uses_correct_script(self, tmp_path, monkeypatch):
        import sys
        monkeypatch.setattr(ep, "DATA_DIR", tmp_path)
        monkeypatch.setattr(ep, "GCS_BUCKET", "")

        with patch("subprocess.run") as mock_sub:
            ep._build_from_scratch()

        args = mock_sub.call_args[0][0]
        assert args[0] == sys.executable
        assert args[-1] == "setup"
        assert "actor_game.py" in args[-2]
