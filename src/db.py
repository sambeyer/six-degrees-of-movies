"""Database connection, schema constants, and the IMDB data build pipeline."""

import gzip
import os
import sqlite3
import sys
from pathlib import Path

import click
from tqdm import tqdm

_default_data_dir = Path.home() / ".actor-game"
DATA_DIR = Path(os.environ.get("ACTOR_GAME_DATA_DIR", _default_data_dir))
DB_PATH = DATA_DIR / "imdb.db"

IMDB_URLS = {
    "name.basics.tsv.gz": "https://datasets.imdbws.com/name.basics.tsv.gz",
    "title.basics.tsv.gz": "https://datasets.imdbws.com/title.basics.tsv.gz",
    "title.principals.tsv.gz": "https://datasets.imdbws.com/title.principals.tsv.gz",
    "title.ratings.tsv.gz": "https://datasets.imdbws.com/title.ratings.tsv.gz",
}

# Title types to include. Use --movies-only to restrict to movie/tvMovie.
ALL_TITLE_TYPES = frozenset(["movie", "tvMovie", "tvSeries", "tvMiniSeries"])
MOVIE_ONLY_TYPES = frozenset(["movie", "tvMovie"])
ACTOR_CATEGORIES = frozenset(["actor", "actress"])

BATCH_SIZE = 50_000


def open_db() -> sqlite3.Connection:
    if not DB_PATH.exists():
        click.echo("Database not found. Run `actor-game setup` first.", err=True)
        sys.exit(1)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _has_ratings(conn: sqlite3.Connection) -> bool:
    return bool(conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='ratings'"
    ).fetchone())


def build_database(data_dir: Path, db_path: Path, title_types: frozenset) -> None:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.executescript("""
        PRAGMA journal_mode=WAL;
        PRAGMA synchronous=NORMAL;
        PRAGMA cache_size=-131072;

        CREATE TABLE IF NOT EXISTS actors (
            nconst    TEXT PRIMARY KEY,
            name      TEXT NOT NULL,
            max_votes INTEGER,
            known_for TEXT
        );
        CREATE TABLE IF NOT EXISTS movies (
            tconst TEXT PRIMARY KEY,
            title  TEXT NOT NULL,
            year   TEXT,
            type   TEXT
        );
        CREATE TABLE IF NOT EXISTS appearances (
            nconst TEXT NOT NULL,
            tconst TEXT NOT NULL,
            PRIMARY KEY (nconst, tconst)
        );
        CREATE TABLE IF NOT EXISTS ratings (
            tconst     TEXT PRIMARY KEY,
            avg_rating REAL,
            num_votes  INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_app_tconst ON appearances(tconst);
        CREATE INDEX IF NOT EXISTS idx_app_nconst ON appearances(nconst);
        CREATE INDEX IF NOT EXISTS idx_actors_name ON actors(name);
    """)
    conn.commit()

    # Migrate existing actors table if it's missing the new columns
    existing_cols = {row[1] for row in cur.execute("PRAGMA table_info(actors)").fetchall()}
    if "max_votes" not in existing_cols:
        cur.execute("ALTER TABLE actors ADD COLUMN max_votes INTEGER")
    if "known_for" not in existing_cols:
        cur.execute("ALTER TABLE actors ADD COLUMN known_for TEXT")
    conn.commit()

    # Check which passes have already been completed
    movies_done = cur.execute("SELECT COUNT(*) FROM movies").fetchone()[0] > 0
    appearances_done = cur.execute("SELECT COUNT(*) FROM appearances").fetchone()[0] > 0
    actors_done = cur.execute("SELECT COUNT(*) FROM actors").fetchone()[0] > 0
    ratings_done = cur.execute("SELECT COUNT(*) FROM ratings").fetchone()[0] > 0
    popularity_done = cur.execute("SELECT COUNT(*) FROM actors WHERE max_votes IS NOT NULL").fetchone()[0] > 0

    # --- Pass 1: load valid movie/show IDs ---
    valid_tconsts: set[str] = set()
    if movies_done:
        click.echo("Step 1/4: movies table already populated, loading IDs from DB ...")
        rows = cur.execute("SELECT tconst FROM movies").fetchall()
        valid_tconsts = {r[0] for r in rows}
        click.echo(f"  {len(valid_tconsts):,} titles loaded from existing DB.")
    else:
        click.echo("Step 1/4: Processing title.basics.tsv.gz ...")
        movie_rows: list[tuple] = []
        with gzip.open(data_dir / "title.basics.tsv.gz", "rt", encoding="utf-8") as f:
            f.readline()  # consume header
            for line in tqdm(f, desc="  titles", unit=" rows", unit_scale=True):
                parts = line.rstrip("\n").split("\t")
                if len(parts) < 6:
                    continue
                tconst, title_type, primary_title, _, is_adult, start_year = parts[:6]
                if title_type in title_types and is_adult == "0":
                    valid_tconsts.add(tconst)
                    movie_rows.append((tconst, primary_title, start_year if start_year != "\\N" else None, title_type))
        click.echo(f"  {len(valid_tconsts):,} valid titles loaded.")
        cur.executemany("INSERT OR IGNORE INTO movies VALUES (?,?,?,?)", movie_rows)
        conn.commit()
        del movie_rows

    # --- Pass 2: load actor<->movie links ---
    valid_nconsts: set[str] = set()
    if appearances_done:
        click.echo("Step 2/4: appearances table already populated, skipping.")
        rows = cur.execute("SELECT DISTINCT nconst FROM appearances").fetchall()
        valid_nconsts = {r[0] for r in rows}
    else:
        click.echo("Step 2/4: Processing title.principals.tsv.gz ...")
        appearance_rows: list[tuple] = []
        with gzip.open(data_dir / "title.principals.tsv.gz", "rt", encoding="utf-8") as f:
            f.readline()  # header
            for line in tqdm(f, desc="  principals", unit=" rows", unit_scale=True):
                parts = line.rstrip("\n").split("\t")
                if len(parts) < 4:
                    continue
                tconst, _, nconst, category = parts[:4]
                if tconst in valid_tconsts and category in ACTOR_CATEGORIES:
                    valid_nconsts.add(nconst)
                    appearance_rows.append((nconst, tconst))
                    if len(appearance_rows) >= BATCH_SIZE:
                        cur.executemany("INSERT OR IGNORE INTO appearances VALUES (?,?)", appearance_rows)
                        appearance_rows.clear()
        if appearance_rows:
            cur.executemany("INSERT OR IGNORE INTO appearances VALUES (?,?)", appearance_rows)
        conn.commit()
        click.echo(f"  {len(valid_nconsts):,} actors/actresses loaded.")

    # --- Pass 3: load actor names ---
    if actors_done:
        click.echo("Step 3/4: actors table already populated, skipping.")
    else:
        click.echo("Step 3/4: Processing name.basics.tsv.gz ...")
        actor_rows: list[tuple] = []
        with gzip.open(data_dir / "name.basics.tsv.gz", "rt", encoding="utf-8") as f:
            f.readline()  # header
            for line in tqdm(f, desc="  names", unit=" rows", unit_scale=True):
                parts = line.rstrip("\n").split("\t")
                if len(parts) < 2:
                    continue
                nconst, primary_name = parts[0], parts[1]
                if nconst in valid_nconsts:
                    actor_rows.append((nconst, primary_name))
                    if len(actor_rows) >= BATCH_SIZE:
                        cur.executemany(
                            "INSERT OR IGNORE INTO actors (nconst, name) VALUES (?,?)",
                            actor_rows,
                        )
                        actor_rows.clear()
        if actor_rows:
            cur.executemany(
                "INSERT OR IGNORE INTO actors (nconst, name) VALUES (?,?)",
                actor_rows,
            )
        conn.commit()

    # --- Pass 4: load ratings ---
    if ratings_done:
        click.echo("Step 4/4: ratings table already populated, skipping.")
    else:
        click.echo("Step 4/4: Processing title.ratings.tsv.gz ...")
        ratings_rows: list[tuple] = []
        with gzip.open(data_dir / "title.ratings.tsv.gz", "rt", encoding="utf-8") as f:
            f.readline()  # header
            for line in tqdm(f, desc="  ratings", unit=" rows", unit_scale=True):
                parts = line.rstrip("\n").split("\t")
                if len(parts) < 3:
                    continue
                tconst, avg_rating, num_votes = parts[0], parts[1], parts[2]
                if tconst in valid_tconsts:
                    try:
                        ratings_rows.append((tconst, float(avg_rating), int(num_votes)))
                    except ValueError:
                        continue
                    if len(ratings_rows) >= BATCH_SIZE:
                        cur.executemany("INSERT OR IGNORE INTO ratings VALUES (?,?,?)", ratings_rows)
                        ratings_rows.clear()
        if ratings_rows:
            cur.executemany("INSERT OR IGNORE INTO ratings VALUES (?,?,?)", ratings_rows)
        conn.commit()

    # --- Pass 5: pre-compute actor popularity (max_votes + known_for) ---
    if popularity_done:
        click.echo("Step 5/5: actor popularity already computed, skipping.")
    else:
        click.echo("Step 5/5: Pre-computing actor popularity ...")
        cur.executescript("""
            UPDATE actors SET
                max_votes = (
                    SELECT MAX(r.num_votes)
                    FROM appearances ap
                    JOIN ratings r ON ap.tconst = r.tconst
                    WHERE ap.nconst = actors.nconst
                ),
                known_for = (
                    SELECT m.title
                    FROM appearances ap
                    JOIN ratings r ON ap.tconst = r.tconst
                    JOIN movies m ON ap.tconst = m.tconst
                    WHERE ap.nconst = actors.nconst
                    ORDER BY r.num_votes DESC
                    LIMIT 1
                );
        """)
        conn.commit()
        click.echo("  Done.")

    conn.close()
    click.echo("Database build complete.")
