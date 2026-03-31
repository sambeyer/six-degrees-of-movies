"""Integration tests for the API endpoints."""

import pytest


def _random_actors(client):
    """Fetch two actors from the live DB."""
    r = client.get("/api/random-actors")
    r.raise_for_status()
    return r.json()


class TestInfo:
    def test_returns_200(self, client):
        assert client.get("/api/info").status_code == 200

    def test_response_shape(self, client):
        data = client.get("/api/info").json()
        assert isinstance(data["actors"], int)
        assert isinstance(data["movies"], int)
        assert isinstance(data["appearances"], int)
        assert isinstance(data["has_ratings"], bool)
        assert isinstance(data["size_mb"], float)

    def test_db_is_populated(self, client):
        data = client.get("/api/info").json()
        assert data["actors"] > 0, "No actors in DB"
        assert data["movies"] > 0, "No movies in DB"
        assert data["appearances"] > 0, "No appearances in DB"


class TestRandomActors:
    def test_returns_200(self, client):
        assert client.get("/api/random-actors").status_code == 200

    def test_returns_two_actors(self, client):
        assert len(client.get("/api/random-actors").json()) == 2

    def test_actor_shape(self, client):
        for actor in client.get("/api/random-actors").json():
            assert "nconst" in actor
            assert "name" in actor
            assert actor["nconst"].startswith("nm")
            assert len(actor["name"]) > 0


class TestSearch:
    def test_short_query_returns_empty(self, client):
        assert client.get("/api/search?q=A").json() == []

    def test_empty_query_returns_empty(self, client):
        assert client.get("/api/search?q=").json() == []

    def test_valid_query_returns_results(self, client):
        fragment = _random_actors(client)[0]["name"][:3]
        r = client.get(f"/api/search?q={fragment}")
        assert r.status_code == 200
        assert len(r.json()) > 0

    def test_result_shape(self, client):
        fragment = _random_actors(client)[0]["name"][:3]
        for item in client.get(f"/api/search?q={fragment}").json():
            assert "nconst" in item
            assert "name" in item
            assert "known_for" in item

    def test_no_match_returns_empty(self, client):
        assert client.get("/api/search?q=Zzznobodyxxx").json() == []

    def test_limit_parameter_respected(self, client):
        fragment = _random_actors(client)[0]["name"][:2]
        assert len(client.get(f"/api/search?q={fragment}&limit=3").json()) <= 3


class TestConnect:
    def test_fewer_than_two_actors_returns_400(self, client):
        actors = _random_actors(client)
        r = client.post("/api/connect", json={"actors": [{"nconst": actors[0]["nconst"]}]})
        assert r.status_code == 400

    def test_unknown_actor_returns_404(self, client):
        actors = _random_actors(client)
        r = client.post("/api/connect", json={
            "actors": [{"nconst": actors[0]["nconst"]}, {"nconst": "nm0000000"}]
        })
        assert r.status_code == 404

    def test_valid_request_returns_200(self, client):
        actors = _random_actors(client)
        r = client.post("/api/connect", json={
            "actors": [{"nconst": actors[0]["nconst"]}, {"nconst": actors[1]["nconst"]}]
        })
        assert r.status_code == 200

    def test_response_shape(self, client):
        actors = _random_actors(client)
        data = client.post("/api/connect", json={
            "actors": [{"nconst": actors[0]["nconst"]}, {"nconst": actors[1]["nconst"]}]
        }).json()
        assert isinstance(data["paths"], list)
        assert isinstance(data["elapsed_ms"], int)

    def test_path_structure_when_found(self, client):
        actors = _random_actors(client)
        paths = client.post("/api/connect", json={
            "actors": [{"nconst": actors[0]["nconst"]}, {"nconst": actors[1]["nconst"]}]
        }).json()["paths"]

        if not paths:
            pytest.skip("No path found between the sampled actors")

        leg = paths[0]["legs"][0]
        assert leg["degrees"] == len(leg["steps"]) - 1
        for key in ("actor", "nconst", "movie", "movie_year", "movie_type", "movie_rating"):
            assert key in leg["steps"][0]

    def test_same_actor_both_ends_returns_zero_degrees(self, client):
        nconst = _random_actors(client)[0]["nconst"]
        paths = client.post("/api/connect", json={
            "actors": [{"nconst": nconst}, {"nconst": nconst}]
        }).json()["paths"]
        assert len(paths) == 1
        assert paths[0]["total_degrees"] == 0

    def test_movies_only_filter_accepted(self, client):
        actors = _random_actors(client)
        r = client.post("/api/connect", json={
            "actors": [{"nconst": actors[0]["nconst"]}, {"nconst": actors[1]["nconst"]}],
            "filters": {"movies_only": True},
        })
        assert r.status_code == 200

    def test_too_many_branch_combos_returns_400(self, client):
        actors = _random_actors(client)
        slot = [{"nconst": actors[0]["nconst"]}, {"nconst": actors[1]["nconst"]}]
        r = client.post("/api/connect", json={"actors": [slot, slot, slot, slot]})
        assert r.status_code == 400
