"""Tests for GCS helper functions (gcs_db module).

All tests mock gcs_db._bucket to avoid any real GCS calls.
"""

from unittest.mock import MagicMock, call, patch

import pytest

import gcs_db


BUCKET = "test-bucket"


def _mock_bucket():
    """Return a (bucket_mock, blob_mock) pair pre-wired together."""
    blob = MagicMock()
    bucket = MagicMock()
    bucket.blob.return_value = blob
    return bucket, blob


class TestDbExists:
    def test_returns_true_when_blob_exists(self):
        bucket, blob = _mock_bucket()
        blob.exists.return_value = True
        with patch("gcs_db._bucket", return_value=bucket):
            assert gcs_db.db_exists(BUCKET) is True

    def test_returns_false_when_blob_missing(self):
        bucket, blob = _mock_bucket()
        blob.exists.return_value = False
        with patch("gcs_db._bucket", return_value=bucket):
            assert gcs_db.db_exists(BUCKET) is False


class TestDownloadDb:
    def test_calls_download_to_filename(self, tmp_path):
        bucket, blob = _mock_bucket()
        blob.size = 500_000_000
        dest = str(tmp_path / "imdb.db")
        with patch("gcs_db._bucket", return_value=bucket):
            gcs_db.download_db(BUCKET, dest)
        blob.reload.assert_called_once()
        blob.download_to_filename.assert_called_once_with(dest)

    def test_handles_none_blob_size(self, tmp_path):
        bucket, blob = _mock_bucket()
        blob.size = None
        dest = str(tmp_path / "imdb.db")
        with patch("gcs_db._bucket", return_value=bucket):
            gcs_db.download_db(BUCKET, dest)  # must not raise
        blob.download_to_filename.assert_called_once()


class TestSyncRawFromGcs:
    def test_downloads_missing_file(self, tmp_path):
        bucket, blob = _mock_bucket()
        blob.exists.return_value = True
        with patch("gcs_db._bucket", return_value=bucket):
            gcs_db.sync_raw_from_gcs(BUCKET, str(tmp_path))
        # All 4 raw files should have been attempted
        assert blob.download_to_filename.call_count == len(gcs_db.RAW_FILES)

    def test_skips_existing_local_file(self, tmp_path):
        # Create one of the raw files locally
        existing = gcs_db.RAW_FILES[0]
        (tmp_path / existing).touch()

        bucket, blob = _mock_bucket()
        blob.exists.return_value = True
        with patch("gcs_db._bucket", return_value=bucket):
            gcs_db.sync_raw_from_gcs(BUCKET, str(tmp_path))
        # Only the 3 missing files should have been downloaded
        assert blob.download_to_filename.call_count == len(gcs_db.RAW_FILES) - 1

    def test_skips_file_absent_in_gcs(self, tmp_path):
        bucket, blob = _mock_bucket()
        blob.exists.return_value = False
        with patch("gcs_db._bucket", return_value=bucket):
            gcs_db.sync_raw_from_gcs(BUCKET, str(tmp_path))
        blob.download_to_filename.assert_not_called()


class TestUploadAll:
    def test_uploads_present_files(self, tmp_path):
        (tmp_path / "imdb.db").touch()
        (tmp_path / gcs_db.RAW_FILES[0]).touch()

        bucket, blob = _mock_bucket()
        with patch("gcs_db._bucket", return_value=bucket):
            gcs_db.upload_all(BUCKET, str(tmp_path))
        assert blob.upload_from_filename.call_count == 2

    def test_skips_absent_files(self, tmp_path):
        # No files present at all
        bucket, blob = _mock_bucket()
        with patch("gcs_db._bucket", return_value=bucket):
            gcs_db.upload_all(BUCKET, str(tmp_path))
        blob.upload_from_filename.assert_not_called()

    def test_uploads_db_and_all_raw_files_when_all_present(self, tmp_path):
        (tmp_path / "imdb.db").touch()
        for f in gcs_db.RAW_FILES:
            (tmp_path / f).touch()

        bucket, blob = _mock_bucket()
        with patch("gcs_db._bucket", return_value=bucket):
            gcs_db.upload_all(BUCKET, str(tmp_path))
        assert blob.upload_from_filename.call_count == 1 + len(gcs_db.RAW_FILES)
