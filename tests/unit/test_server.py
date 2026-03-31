"""Tests for the FastAPI server (endpoints and helpers)."""

import sqlite3
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

import db as db_mod
import server as server_mod
from server import _client_ip, app


@pytest.fixture
def client(db_path, monkeypatch):
    """TestClient backed by the test database."""
    monkeypatch.setattr(db_mod, "DB_PATH", db_path)
    monkeypatch.setattr(server_mod, "DB_PATH", db_path)
    # open_db reads db_mod.DB_PATH at call time, so patching db_mod is enough.
    # server_mod.DB_PATH patch covers the /api/info endpoint which uses it directly.
    return TestClient(app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# _client_ip
# ---------------------------------------------------------------------------

class TestClientIp:
    def _req(self, forwarded=None, host=None):
        req = MagicMock()
        req.headers.get = lambda key, default=None: forwarded if key == "X-Forwarded-For" else default
        req.client = MagicMock(host=host) if host else None
        return req

    def test_uses_first_forwarded_ip(self):
        assert _client_ip(self._req(forwarded="1.2.3.4, 5.6.7.8")) == "1.2.3.4"

    def test_strips_whitespace_from_forwarded(self):
        assert _client_ip(self._req(forwarded="  9.9.9.9  ")) == "9.9.9.9"

    def test_falls_back_to_client_host(self):
        assert _client_ip(self._req(host="10.0.0.1")) == "10.0.0.1"

    def test_returns_unknown_when_no_info(self):
        assert _client_ip(self._req()) == "unknown"


# ---------------------------------------------------------------------------
# GET /api/search
# ---------------------------------------------------------------------------

class TestSearch:
    def test_short_query_returns_empty(self, client):
        r = client.get("/api/search?q=A")
        assert r.status_code == 200
        assert r.json() == []

    def test_empty_query_returns_empty(self, client):
        r = client.get("/api/search?q=")
        assert r.status_code == 200
        assert r.json() == []

    def test_matching_query_returns_results(self, client):
        r = client.get("/api/search?q=Ali")
        assert r.status_code == 200
        data = r.json()
        assert any(a["name"] == "Alice" for a in data)

    def test_result_shape(self, client):
        r = client.get("/api/search?q=Ali")
        for item in r.json():
            assert "nconst" in item
            assert "name" in item
            assert "known_for" in item

    def test_no_match_returns_empty(self, client):
        r = client.get("/api/search?q=Zzznobody")
        assert r.status_code == 200
        assert r.json() == []


# ---------------------------------------------------------------------------
# POST /api/connect
# ---------------------------------------------------------------------------

class TestConnect:
    def test_fewer_than_two_actors_returns_400(self, client):
        r = client.post("/api/connect", json={"actors": [{"nconst": "nm001"}]})
        assert r.status_code == 400

    def test_unknown_actor_returns_404(self, client):
        r = client.post("/api/connect", json={
            "actors": [{"nconst": "nm001"}, {"nconst": "nm999"}]
        })
        assert r.status_code == 404

    def test_valid_connection_returns_path(self, client):
        r = client.post("/api/connect", json={
            "actors": [{"nconst": "nm001"}, {"nconst": "nm002"}]
        })
        assert r.status_code == 200
        data = r.json()
        assert len(data["paths"]) > 0
        assert data["paths"][0]["legs"][0]["degrees"] == 1

    def test_no_path_returns_empty_paths(self, client):
        r = client.post("/api/connect", json={
            "actors": [{"nconst": "nm001"}, {"nconst": "nm005"}]
        })
        assert r.status_code == 200
        assert r.json()["paths"] == []

    def test_response_has_elapsed_ms(self, client):
        r = client.post("/api/connect", json={
            "actors": [{"nconst": "nm001"}, {"nconst": "nm002"}]
        })
        assert r.status_code == 200
        assert isinstance(r.json()["elapsed_ms"], int)
        assert r.json()["elapsed_ms"] >= 0

    def test_movies_only_filter_applied(self, client):
        # Carol↔Dave only share a tvSeries; movies_only should make it unreachable
        r = client.post("/api/connect", json={
            "actors": [{"nconst": "nm003"}, {"nconst": "nm004"}],
            "filters": {"movies_only": True},
        })
        assert r.status_code == 200
        assert r.json()["paths"] == []

    def test_too_many_branch_combos_returns_400(self, client):
        # 4 slots each with 2 alternatives → 16 combos, over the 12-combo limit
        slot = [{"nconst": "nm001"}, {"nconst": "nm002"}]
        r = client.post("/api/connect", json={"actors": [slot, slot, slot, slot]})
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# GET /api/random-actors
# ---------------------------------------------------------------------------

class TestRandomActors:
    def test_returns_two_actors(self, client):
        r = client.get("/api/random-actors")
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 2

    def test_result_has_nconst_and_name(self, client):
        r = client.get("/api/random-actors")
        for item in r.json():
            assert "nconst" in item
            assert "name" in item


# ---------------------------------------------------------------------------
# GET /api/info
# ---------------------------------------------------------------------------

class TestInfo:
    def test_returns_stats(self, client):
        r = client.get("/api/info")
        assert r.status_code == 200
        data = r.json()
        assert data["actors"] == 5
        assert data["movies"] == 5
        assert data["appearances"] == 10
        assert data["has_ratings"] is True
        assert isinstance(data["size_mb"], float)

    def test_missing_db_returns_503(self, tmp_path, monkeypatch):
        missing = tmp_path / "nonexistent.db"
        monkeypatch.setattr(server_mod, "DB_PATH", missing)
        r = TestClient(app).get("/api/info")
        assert r.status_code == 503
