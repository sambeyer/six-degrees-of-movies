"""Tests for BFS path-finding (bfs, bfs_multi)."""

import pytest

from bfs import bfs, bfs_multi

PATH_STEP_KEYS = {"actor", "nconst", "movie", "movie_year", "movie_type", "movie_rating", "movie_tconst"}


class TestBfs:
    # --- basic connectivity ---

    def test_same_actor_returns_single_step(self, conn):
        result = bfs(conn, "nm001", "nm001", max_depth=6)
        assert result is not None
        assert len(result) == 1
        assert result[0]["actor"] == "Alice"
        assert result[0]["movie"] is None

    def test_one_degree(self, conn):
        result = bfs(conn, "nm001", "nm002", max_depth=6)
        assert result is not None
        assert len(result) == 2
        assert result[0]["actor"] == "Alice"
        assert result[1]["actor"] == "Bob"

    def test_two_degrees(self, conn):
        # Alice → Carol → Dave (only Carol connects them)
        result = bfs(conn, "nm001", "nm004", max_depth=6)
        assert result is not None
        assert len(result) == 3
        assert result[0]["actor"] == "Alice"
        assert result[-1]["actor"] == "Dave"

    def test_unreachable_returns_none(self, conn):
        assert bfs(conn, "nm001", "nm005", max_depth=6) is None

    def test_unknown_nconst_returns_none(self, conn):
        assert bfs(conn, "nm001", "nm999", max_depth=6) is None

    def test_max_depth_blocks_long_path(self, conn):
        # Alice→Dave needs 2 hops; max_depth=1 must return None
        assert bfs(conn, "nm001", "nm004", max_depth=1) is None

    # --- filter: movies_only ---

    def test_movies_only_excludes_tv_series(self, conn):
        # Carol↔Dave only share Movie Three (tvSeries)
        assert bfs(conn, "nm003", "nm004", max_depth=6, movies_only=True) is None

    def test_movies_only_allows_movie_paths(self, conn):
        # Movie One is a movie — Alice↔Bob unaffected
        assert bfs(conn, "nm001", "nm002", max_depth=6, movies_only=True) is not None

    # --- filter: min_year ---

    def test_min_year_cuts_off_old_movies(self, conn):
        # min_year=2013 excludes tt001 (2010), tt004 (2005), tt005 (2012)
        # Alice has no appearances in valid movies → can't reach Bob
        assert bfs(conn, "nm001", "nm002", max_depth=6, min_year=2013) is None

    def test_min_year_keeps_recent_path(self, conn):
        # Bob↔Carol via Movie Two (2015) is fine with min_year=2013
        result = bfs(conn, "nm002", "nm003", max_depth=6, min_year=2013)
        assert result is not None

    # --- filter: min_rating ---

    def test_min_rating_cuts_low_rated_path(self, conn):
        # Movie Three (6.0) excluded; Carol↔Dave disconnected with min_rating=7.0
        assert bfs(conn, "nm003", "nm004", max_depth=6, min_rating=7.0) is None

    def test_min_rating_allows_high_rated_path(self, conn):
        # Movie One (8.0) passes min_rating=7.5
        result = bfs(conn, "nm001", "nm002", max_depth=6, min_rating=7.5)
        assert result is not None

    # --- filter: min_votes ---

    def test_min_votes_cuts_low_vote_movies(self, conn):
        # min_votes=70000: only tt001 (100k) passes.
        # Alice→Carol: tt004 (10k) and tt005 (60k) both excluded → None
        assert bfs(conn, "nm001", "nm003", max_depth=6, min_votes=70_000) is None

    def test_min_votes_allows_high_vote_path(self, conn):
        # Alice↔Bob via tt001 (100k votes) still valid
        result = bfs(conn, "nm001", "nm002", max_depth=6, min_votes=70_000)
        assert result is not None

    # --- filter: no ratings table ---

    def test_rating_filters_ignored_without_ratings_table(self, conn_no_ratings):
        # Without ratings, min_rating and min_votes are silently suppressed
        result = bfs(conn_no_ratings, "nm001", "nm002", max_depth=6, min_rating=9.9, min_votes=999_999)
        assert result is not None

    # --- filter: forbidden ---

    def test_forbidden_blocks_direct_target(self, conn):
        assert bfs(conn, "nm001", "nm002", max_depth=6, forbidden={"nm002"}) is None

    def test_forbidden_forces_reroute_to_none(self, conn):
        # All paths to Dave pass through Carol
        assert bfs(conn, "nm001", "nm004", max_depth=6, forbidden={"nm003"}) is None

    # --- path shape ---

    def test_first_step_has_no_movie(self, conn):
        result = bfs(conn, "nm001", "nm002", max_depth=6)
        assert result[0]["movie"] is None
        assert result[0]["movie_tconst"] is None

    def test_step_has_all_required_keys(self, conn):
        result = bfs(conn, "nm001", "nm002", max_depth=6)
        for step in result:
            assert PATH_STEP_KEYS == set(step.keys())

    def test_step_includes_movie_details(self, conn):
        result = bfs(conn, "nm001", "nm002", max_depth=6)
        step = result[1]  # Bob, connected via Movie One
        assert step["movie_tconst"] == "tt001"
        assert step["movie_year"] == 2010   # int, not string
        assert step["movie_type"] == "movie"
        assert step["movie_rating"] == 8.0

    def test_step_nconsts_are_correct(self, conn):
        result = bfs(conn, "nm001", "nm002", max_depth=6)
        assert result[0]["nconst"] == "nm001"
        assert result[1]["nconst"] == "nm002"


class TestBfsMulti:
    def test_returns_multiple_shortest_paths(self, conn):
        # Alice→Carol: two 1-hop edges (tt004 and tt005)
        results = bfs_multi(conn, "nm001", "nm003", max_depth=6, k=5)
        assert len(results) >= 2

    def test_all_paths_have_equal_length(self, conn):
        results = bfs_multi(conn, "nm001", "nm003", max_depth=6, k=5)
        lengths = {len(p) for p in results}
        assert len(lengths) == 1

    def test_all_paths_start_and_end_correctly(self, conn):
        results = bfs_multi(conn, "nm001", "nm003", max_depth=6, k=5)
        for path in results:
            assert path[0]["actor"] == "Alice"
            assert path[-1]["actor"] == "Carol"

    def test_respects_k_limit(self, conn):
        results = bfs_multi(conn, "nm001", "nm003", max_depth=6, k=1)
        assert len(results) == 1

    def test_no_path_returns_empty_list(self, conn):
        assert bfs_multi(conn, "nm001", "nm005", max_depth=6) == []

    def test_same_actor_returns_single_step_path(self, conn):
        results = bfs_multi(conn, "nm001", "nm001", max_depth=6)
        assert len(results) == 1
        assert len(results[0]) == 1

    def test_path_steps_have_all_keys(self, conn):
        results = bfs_multi(conn, "nm001", "nm003", max_depth=6)
        for path in results:
            for step in path:
                assert PATH_STEP_KEYS == set(step.keys())

    def test_distinct_movies_across_paths(self, conn):
        # The two paths should differ in which movie connects Alice to Carol
        results = bfs_multi(conn, "nm001", "nm003", max_depth=6, k=5)
        tconsts = {path[1]["movie_tconst"] for path in results}
        assert len(tconsts) > 1  # different movies used
