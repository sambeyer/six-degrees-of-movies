"""Shared fixtures for the test suite.

Test graph
----------
Actors:  nm001 Alice / nm002 Bob / nm003 Carol / nm004 Dave / nm005 Eve (isolated)

Movies:
  tt001  Movie One    2010  movie     8.0 / 100 000 votes  → Alice + Bob
  tt002  Movie Two    2015  movie     7.0 /  50 000 votes  → Bob + Carol
  tt003  Movie Three  2020  tvSeries  6.0 /  20 000 votes  → Carol + Dave
  tt004  Movie Four   2005  movie     5.0 /  10 000 votes  → Alice + Carol
  tt005  Movie Five   2012  movie     7.5 /  60 000 votes  → Alice + Carol

Shortest paths (unfiltered):
  Alice → Bob    1 hop (tt001)
  Alice → Carol  1 hop (tt004 or tt005)
  Alice → Dave   2 hops (Alice → Carol → Dave)
  Alice → Eve    unreachable
"""

import sqlite3

import pytest


_ACTORS = [
    ("nm001", "Alice",  500_000, "Movie One"),
    ("nm002", "Bob",    600_000, "Movie One"),
    ("nm003", "Carol",  100_000, "Movie Two"),
    ("nm004", "Dave",    50_000, "Movie Three"),
    ("nm005", "Eve",          0, None),
]

_MOVIES = [
    ("tt001", "Movie One",   "2010", "movie"),
    ("tt002", "Movie Two",   "2015", "movie"),
    ("tt003", "Movie Three", "2020", "tvSeries"),
    ("tt004", "Movie Four",  "2005", "movie"),
    ("tt005", "Movie Five",  "2012", "movie"),
]

_APPEARANCES = [
    ("nm001", "tt001"),  # Alice  in Movie One
    ("nm002", "tt001"),  # Bob    in Movie One
    ("nm002", "tt002"),  # Bob    in Movie Two
    ("nm003", "tt002"),  # Carol  in Movie Two
    ("nm003", "tt003"),  # Carol  in Movie Three
    ("nm004", "tt003"),  # Dave   in Movie Three
    ("nm001", "tt004"),  # Alice  in Movie Four
    ("nm003", "tt004"),  # Carol  in Movie Four
    ("nm001", "tt005"),  # Alice  in Movie Five
    ("nm003", "tt005"),  # Carol  in Movie Five
]

_RATINGS = [
    ("tt001", 8.0, 100_000),
    ("tt002", 7.0,  50_000),
    ("tt003", 6.0,  20_000),
    ("tt004", 5.0,  10_000),
    ("tt005", 7.5,  60_000),
]

_DDL_BASE = """
    CREATE TABLE actors (
        nconst    TEXT PRIMARY KEY,
        name      TEXT NOT NULL,
        max_votes INTEGER,
        known_for TEXT
    );
    CREATE TABLE movies (
        tconst TEXT PRIMARY KEY,
        title  TEXT NOT NULL,
        year   TEXT,
        type   TEXT
    );
    CREATE TABLE appearances (
        nconst TEXT NOT NULL,
        tconst TEXT NOT NULL,
        PRIMARY KEY (nconst, tconst)
    );
    CREATE INDEX idx_app_tconst ON appearances(tconst);
    CREATE INDEX idx_app_nconst ON appearances(nconst);
    CREATE INDEX idx_actors_name ON actors(name);
"""

_DDL_RATINGS = """
    CREATE TABLE ratings (
        tconst     TEXT PRIMARY KEY,
        avg_rating REAL,
        num_votes  INTEGER
    );
"""


def _populate(conn: sqlite3.Connection, include_ratings: bool = True) -> None:
    conn.executescript(_DDL_BASE)
    if include_ratings:
        conn.executescript(_DDL_RATINGS)
    conn.executemany(
        "INSERT INTO actors (nconst, name, max_votes, known_for) VALUES (?,?,?,?)",
        _ACTORS,
    )
    conn.executemany("INSERT INTO movies VALUES (?,?,?,?)", _MOVIES)
    conn.executemany("INSERT INTO appearances VALUES (?,?)", _APPEARANCES)
    if include_ratings:
        conn.executemany("INSERT INTO ratings VALUES (?,?,?)", _RATINGS)
    conn.commit()


@pytest.fixture
def conn():
    """In-memory SQLite database with ratings table."""
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    _populate(db)
    yield db
    db.close()


@pytest.fixture
def conn_no_ratings():
    """In-memory SQLite database without the ratings table."""
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    _populate(db, include_ratings=False)
    yield db
    db.close()


@pytest.fixture
def db_path(tmp_path):
    """File-based SQLite database used by tests that need a real filesystem path."""
    path = tmp_path / "test.db"
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    _populate(db)
    db.close()
    return path
