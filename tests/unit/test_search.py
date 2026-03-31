"""Tests for actor search helpers (_has_ratings, search_actors, pick_actor)."""

from unittest.mock import patch

import pytest

import search as search_mod
from db import _has_ratings
from search import pick_actor, search_actors


class TestHasRatings:
    def test_returns_true_with_ratings_table(self, conn):
        assert _has_ratings(conn) is True

    def test_returns_false_without_ratings_table(self, conn_no_ratings):
        assert _has_ratings(conn_no_ratings) is False


class TestSearchActors:
    def test_exact_name_match(self, conn):
        results = search_actors(conn, "Alice")
        assert len(results) == 1
        assert results[0]["name"] == "Alice"
        assert results[0]["nconst"] == "nm001"

    def test_partial_name_match(self, conn):
        # "a" matches Alice, Carol, Dave (and possibly Bob — Bob has no 'a', Carol has 'a')
        # Alice, Carol have 'a' — check at least one is returned
        results = search_actors(conn, "al")
        names = [r["name"] for r in results]
        assert "Alice" in names

    def test_case_insensitive_match(self, conn):
        results = search_actors(conn, "alice")
        assert any(r["name"] == "Alice" for r in results)

    def test_no_match_returns_empty_list(self, conn):
        results = search_actors(conn, "Zzznobody")
        assert results == []

    def test_returns_plain_dicts(self, conn):
        results = search_actors(conn, "Alice")
        assert isinstance(results[0], dict)
        assert "nconst" in results[0]
        assert "name" in results[0]

    def test_mid_name_match(self, conn):
        # "ob" is in "Bob"
        results = search_actors(conn, "ob")
        assert any(r["name"] == "Bob" for r in results)


class TestPickActor:
    def test_single_match_returned_directly(self):
        matches = [{"nconst": "nm001", "name": "Alice"}]
        assert pick_actor(matches, "anything") == matches[0]

    def test_exact_case_insensitive_match(self):
        matches = [
            {"nconst": "nm001", "name": "Alice"},
            {"nconst": "nm006", "name": "Alice Wonder"},
        ]
        result = pick_actor(matches, "alice")
        assert result["nconst"] == "nm001"

    def test_multiple_matches_prompts_and_returns_choice(self):
        matches = [
            {"nconst": "nm001", "name": "Tom Hanks"},
            {"nconst": "nm002", "name": "Tom Hardy"},
        ]
        with patch.object(search_mod.click, "echo"), \
             patch.object(search_mod.click, "prompt", return_value=2):
            result = pick_actor(matches, "Tom")
        assert result["nconst"] == "nm002"

    def test_out_of_range_choice_returns_none(self):
        matches = [
            {"nconst": "nm001", "name": "Tom Hanks"},
            {"nconst": "nm002", "name": "Tom Hardy"},
        ]
        with patch.object(search_mod.click, "echo"), \
             patch.object(search_mod.click, "prompt", return_value=0):
            result = pick_actor(matches, "Tom")
        assert result is None
