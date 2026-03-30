#!/usr/bin/env python3
"""
Actor Connection Game
Find the shortest path between two actors via shared movies.

Uses IMDB's free datasets, downloaded and stored locally in a SQLite database.
Run `actor-game setup` first to download the data (~1GB download, ~2GB on disk).
"""

import os
import sys
import gzip
import sqlite3
from pathlib import Path
from collections import deque

import click
import requests
from prompt_toolkit import prompt as pt_prompt
from prompt_toolkit.completion import Completer, Completion
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


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

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
            nconst TEXT PRIMARY KEY,
            name   TEXT NOT NULL
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

    # --- Pass 1: load valid movie/show IDs ---
    click.echo("Step 1/3: Processing title.basics.tsv.gz ...")
    valid_tconsts: set[str] = set()
    movie_rows: list[tuple] = []

    with gzip.open(data_dir / "title.basics.tsv.gz", "rt", encoding="utf-8") as f:
        header = f.readline()  # consume header
        for line in tqdm(f, desc="  titles", unit=" rows", unit_scale=True):
            parts = line.rstrip("\n").split("\t")
            # tconst, titleType, primaryTitle, originalTitle, isAdult, startYear, ...
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
    click.echo("Step 2/3: Processing title.principals.tsv.gz ...")
    valid_nconsts: set[str] = set()
    appearance_rows: list[tuple] = []

    with gzip.open(data_dir / "title.principals.tsv.gz", "rt", encoding="utf-8") as f:
        f.readline()  # header
        for line in tqdm(f, desc="  principals", unit=" rows", unit_scale=True):
            parts = line.rstrip("\n").split("\t")
            # tconst, ordering, nconst, category, ...
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
    click.echo("Step 3/3: Processing name.basics.tsv.gz ...")
    actor_rows: list[tuple] = []

    with gzip.open(data_dir / "name.basics.tsv.gz", "rt", encoding="utf-8") as f:
        f.readline()  # header
        for line in tqdm(f, desc="  names", unit=" rows", unit_scale=True):
            parts = line.rstrip("\n").split("\t")
            # nconst, primaryName, ...
            if len(parts) < 2:
                continue
            nconst, primary_name = parts[0], parts[1]
            if nconst in valid_nconsts:
                actor_rows.append((nconst, primary_name))
                if len(actor_rows) >= BATCH_SIZE:
                    cur.executemany("INSERT OR IGNORE INTO actors VALUES (?,?)", actor_rows)
                    actor_rows.clear()

    if actor_rows:
        cur.executemany("INSERT OR IGNORE INTO actors VALUES (?,?)", actor_rows)
    conn.commit()

    # --- Pass 4: load ratings ---
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
    conn.close()
    click.echo("Database built successfully.")


# ---------------------------------------------------------------------------
# BFS path-finding
# ---------------------------------------------------------------------------

def bfs(
    conn: sqlite3.Connection,
    start: str,
    end: str,
    max_depth: int,
    min_year: int | None = None,
    movies_only: bool = False,
    min_rating: float | None = None,
    min_votes: int | None = None,
    forbidden: set[str] | None = None,
) -> list[dict] | None:
    """
    Bidirectional BFS between start and end (nconst IDs).
    Returns ordered list of path steps, or None if not found within max_depth.
    Each step: {"actor": name, "movie": "Title (year)" | None}
    """
    # Silently suppress rating/vote filters if the ratings table hasn't been built yet
    ratings_available = _has_ratings(conn)
    if not ratings_available:
        min_rating = None
        min_votes = None

    if start == end:
        name = conn.execute("SELECT name FROM actors WHERE nconst=?", (start,)).fetchone()["name"]
        return [{"actor": name, "nconst": start, "movie": None, "movie_year": None, "movie_type": None, "movie_rating": None}]

    # Forward and backward frontiers
    # prev_fwd[nconst] = (parent_nconst, via_tconst)
    prev_fwd: dict[str, tuple | None] = {start: None}
    prev_bwd: dict[str, tuple | None] = {end: None}
    frontier_fwd: deque[str] = deque([start])
    frontier_bwd: deque[str] = deque([end])
    depth_fwd: dict[str, int] = {start: 0}
    depth_bwd: dict[str, int] = {end: 0}

    def expand(frontier, prev, depth, other_prev, other_depth, max_d) -> str | None:
        """Expand one level of BFS. Returns meeting nconst if found, else None."""
        next_frontier: deque[str] = deque()
        while frontier:
            current = frontier.popleft()
            cur_d = depth[current]
            if cur_d >= max_d:
                continue
            if min_year or movies_only or min_rating or min_votes:
                conditions = ["a.nconst=?"]
                params: list = [current]
                joins = "JOIN movies m ON a.tconst = m.tconst"
                if min_year:
                    conditions.append("CAST(m.year AS INTEGER) >= ?")
                    params.append(min_year)
                if movies_only:
                    conditions.append("m.type = 'movie'")
                if ratings_available and (min_rating or min_votes):
                    joins += " JOIN ratings r ON a.tconst = r.tconst"
                    if min_rating:
                        conditions.append("r.avg_rating >= ?")
                        params.append(min_rating)
                    if min_votes:
                        conditions.append("r.num_votes >= ?")
                        params.append(min_votes)
                where = " AND ".join(conditions)
                movies = conn.execute(
                    f"SELECT a.tconst FROM appearances a {joins} WHERE {where}",
                    params,
                ).fetchall()
            else:
                movies = conn.execute(
                    "SELECT tconst FROM appearances WHERE nconst=?", (current,)
                ).fetchall()
            for (tconst,) in movies:
                co_actors = conn.execute(
                    "SELECT nconst FROM appearances WHERE tconst=? AND nconst!=?",
                    (tconst, current),
                ).fetchall()
                for (nconst,) in co_actors:
                    if nconst not in prev and (forbidden is None or nconst not in forbidden):
                        prev[nconst] = (current, tconst)
                        depth[nconst] = cur_d + 1
                        next_frontier.append(nconst)
                        if nconst in other_prev:
                            return nconst
        frontier.extend(next_frontier)
        return None

    half = max_depth // 2
    for _ in range(max_depth):
        # Always expand the smaller frontier
        if len(frontier_fwd) <= len(frontier_bwd):
            meeting = expand(frontier_fwd, prev_fwd, depth_fwd, prev_bwd, depth_bwd, half + 1)
        else:
            meeting = expand(frontier_bwd, prev_bwd, depth_bwd, prev_fwd, depth_fwd, half + 1)

        if meeting is not None:
            return _reconstruct(conn, prev_fwd, prev_bwd, start, end, meeting, min_year, movies_only, min_rating, min_votes)

        # Also check if any node in one frontier is known to the other
        for nconst in prev_fwd:
            if nconst in prev_bwd:
                return _reconstruct(conn, prev_fwd, prev_bwd, start, end, nconst, min_year, movies_only, min_rating, min_votes)

        if not frontier_fwd and not frontier_bwd:
            break

    return None


def _reconstruct(
    conn: sqlite3.Connection,
    prev_fwd: dict,
    prev_bwd: dict,
    start: str,
    end: str,
    meeting: str,
    min_year: int | None = None,
    movies_only: bool = False,
    min_rating: float | None = None,
    min_votes: int | None = None,
) -> list[dict]:
    """Build the path list from the bidirectional BFS results."""

    def lookup_actor(nconst):
        row = conn.execute("SELECT name FROM actors WHERE nconst=?", (nconst,)).fetchone()
        return row["name"] if row else nconst

    has_ratings_tbl = _has_ratings(conn)

    def lookup_movie_detail(tconst) -> dict:
        if has_ratings_tbl:
            row = conn.execute(
                "SELECT m.title, m.year, m.type, r.avg_rating"
                " FROM movies m LEFT JOIN ratings r ON m.tconst = r.tconst"
                " WHERE m.tconst=?",
                (tconst,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT title, year, type, NULL as avg_rating FROM movies WHERE tconst=?",
                (tconst,),
            ).fetchone()
        if not row:
            return {"movie": tconst, "movie_year": None, "movie_type": None, "movie_rating": None}
        title = f"{row['title']} ({row['year']})" if row["year"] else row["title"]
        return {
            "movie": title,
            "movie_year": int(row["year"]) if row["year"] and row["year"].isdigit() else None,
            "movie_type": row["type"],
            "movie_rating": row["avg_rating"],
        }

    # Build forward half: start -> meeting
    fwd_nodes: list[str] = []
    cur = meeting
    while cur is not None:
        fwd_nodes.append(cur)
        entry = prev_fwd[cur]
        cur = entry[0] if entry else None
    fwd_nodes.reverse()  # now: [start, ..., meeting]

    # Build backward half: meeting -> end
    bwd_nodes: list[str] = []
    cur = meeting
    while cur is not None:
        bwd_nodes.append(cur)
        entry = prev_bwd[cur]
        cur = entry[0] if entry else None
    # bwd_nodes: [meeting, ..., end]

    full_nodes = fwd_nodes + bwd_nodes[1:]  # avoid duplicating meeting

    # Build path steps with connecting movies
    path: list[dict] = []
    for i, nconst in enumerate(full_nodes):
        if i == 0:
            path.append({"actor": lookup_actor(nconst), "nconst": nconst, "movie": None, "movie_year": None, "movie_type": None, "movie_rating": None})
        else:
            prev_nconst = full_nodes[i - 1]
            # Find the connecting movie.
            # Forward BFS stores: prev_fwd[child] = (parent, movie)
            # Backward BFS stores: prev_bwd[child_toward_end] = (parent_toward_end, movie)
            #   so for a path step prev_nconst→nconst in the backward half,
            #   the movie is in prev_bwd[prev_nconst] where parent == nconst.
            via_tconst = None
            if nconst in prev_fwd and prev_fwd[nconst]:
                parent, tconst = prev_fwd[nconst]
                if parent == prev_nconst:
                    via_tconst = tconst
            if via_tconst is None and prev_nconst in prev_bwd and prev_bwd[prev_nconst]:
                parent, tconst = prev_bwd[prev_nconst]
                if parent == nconst:
                    via_tconst = tconst
            if via_tconst is None:
                # Fallback: find any shared movie respecting active filters
                params: list = [prev_nconst, nconst]
                joins = "JOIN appearances a2 ON a1.tconst = a2.tconst"
                conditions = ["a1.nconst=?", "a2.nconst=?"]
                if min_year or movies_only or min_rating or min_votes:
                    joins += " JOIN movies m ON a1.tconst = m.tconst"
                    if min_year:
                        conditions.append("CAST(m.year AS INTEGER) >= ?")
                        params.append(min_year)
                    if movies_only:
                        conditions.append("m.type = 'movie'")
                    if has_ratings_tbl and (min_rating or min_votes):
                        joins += " JOIN ratings r ON a1.tconst = r.tconst"
                        if min_rating:
                            conditions.append("r.avg_rating >= ?")
                            params.append(min_rating)
                        if min_votes:
                            conditions.append("r.num_votes >= ?")
                            params.append(min_votes)
                where = " AND ".join(conditions)
                row = conn.execute(
                    f"SELECT a1.tconst FROM appearances a1 {joins} WHERE {where} LIMIT 1",
                    params,
                ).fetchone()
                via_tconst = row[0] if row else None

            detail = lookup_movie_detail(via_tconst) if via_tconst else {
                "movie": "?", "movie_year": None, "movie_type": None, "movie_rating": None,
            }
            path.append({"actor": lookup_actor(nconst), "nconst": nconst, **detail})

    return path


# ---------------------------------------------------------------------------
# Actor search & disambiguation
# ---------------------------------------------------------------------------

def search_actors(conn: sqlite3.Connection, name: str) -> list[dict]:
    rows = conn.execute(
        "SELECT nconst, name FROM actors WHERE name LIKE ? LIMIT 15",
        (f"%{name}%",),
    ).fetchall()
    return [dict(r) for r in rows]


def pick_actor(matches: list[dict], query: str) -> dict | None:
    # Prefer exact match
    exact = [m for m in matches if m["name"].lower() == query.lower()]
    if len(exact) == 1:
        return exact[0]
    if len(matches) == 1:
        return matches[0]

    click.echo(f"\nMultiple results for '{query}':")
    for i, m in enumerate(matches, 1):
        click.echo(f"  {i:>2}. {m['name']}  ({m['nconst']})")
    choice = click.prompt("Pick a number (0 to cancel)", type=int, default=1)
    if choice <= 0 or choice > len(matches):
        return None
    return matches[choice - 1]


# ---------------------------------------------------------------------------
# Interactive actor prompt with autocomplete
# ---------------------------------------------------------------------------

class ActorCompleter(Completer):
    """prompt_toolkit Completer that queries the local SQLite actors table."""

    def __init__(self, db_path: Path) -> None:
        # check_same_thread=False lets prompt_toolkit call us from its worker thread
        self._conn = sqlite3.connect(db_path, check_same_thread=False)

    def get_completions(self, document, complete_event):
        word = document.text_before_cursor
        if len(word) < 2:
            return
        # Prefix match first (uses the idx_actors_name index — fast)
        rows = self._conn.execute(
            "SELECT name, nconst FROM actors WHERE name LIKE ? ORDER BY name LIMIT 20",
            (word + "%",),
        ).fetchall()
        # If too few prefix hits, also include mid-name matches
        if len(rows) < 5:
            extra = self._conn.execute(
                "SELECT name, nconst FROM actors WHERE name LIKE ? AND name NOT LIKE ? "
                "ORDER BY name LIMIT 10",
                (f"%{word}%", word + "%"),
            ).fetchall()
            rows = rows + extra
        for name, nconst in rows:
            yield Completion(
                name,
                start_position=-len(word),
                display_meta=nconst,
            )

    def close(self) -> None:
        self._conn.close()


def prompt_actor(
    label: str,
    completer: ActorCompleter,
    conn: sqlite3.Connection,
    optional: bool = False,
) -> dict | None:
    """
    Interactively prompt for an actor name with live autocomplete.

    If optional=True, an empty submission returns None (meaning "done").
    Returns a resolved actor dict, or None if cancelled / done.
    """
    while True:
        try:
            text = pt_prompt(
                f"{label}: ",
                completer=completer,
                complete_while_typing=True,
                complete_in_thread=True,
            )
        except (EOFError, KeyboardInterrupt):
            click.echo()
            return None

        text = text.strip()
        if not text:
            if optional:
                return None
            continue

        matches = search_actors(conn, text)
        if not matches:
            click.echo(f"  No actor found for '{text}'. Try again.")
            continue

        actor = pick_actor(matches, text)
        if actor is not None:
            return actor


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------

@click.group()
def cli():
    """Actor Connection Game — find the shortest path between two actors via shared films."""


@cli.command()
@click.option("--force", is_flag=True, help="Re-download files and rebuild the database.")
@click.option(
    "--movies-only",
    is_flag=True,
    default=False,
    help="Only include movies and TV movies (skip TV series). Smaller DB, fewer connections.",
)
def setup(force: bool, movies_only: bool) -> None:
    """Download IMDB datasets and build a local SQLite database.

    Downloads ~1 GB of compressed data from datasets.imdbws.com and processes
    it into a local SQLite database (~500 MB–1 GB depending on options).
    This only needs to be run once (or when you want to refresh the data).
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    for filename, url in IMDB_URLS.items():
        dest = DATA_DIR / filename
        if dest.exists() and not force:
            click.echo(f"  {filename} already exists, skipping (use --force to re-download).")
        else:
            click.echo(f"Downloading {filename} ...")
            _download(url, dest)

    if DB_PATH.exists() and not force:
        click.echo(f"\nDatabase already exists at {DB_PATH}.")
        conn = sqlite3.connect(DB_PATH)
        # Ensure the name index exists for fast autocomplete (harmless if already present)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_actors_name ON actors(name)")
        conn.commit()
        has_ratings = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='ratings'"
        ).fetchone()
        conn.close()
        if not has_ratings:
            click.echo(
                "  Note: ratings table not found. Run with --force to rebuild "
                "and enable rating/vote filters."
            )
        click.echo("Use --force to rebuild it.")
        return

    if DB_PATH.exists():
        DB_PATH.unlink()

    title_types = MOVIE_ONLY_TYPES if movies_only else ALL_TITLE_TYPES
    click.echo(
        f"\nBuilding database (title types: {', '.join(sorted(title_types))}) ..."
    )
    build_database(DATA_DIR, DB_PATH, title_types)
    click.echo(f"\nAll done. Database saved to {DB_PATH}")


def _resolve_actor_from_name(conn: sqlite3.Connection, name: str) -> dict | None:
    """Look up a named actor non-interactively; prints an error and returns None on failure."""
    matches = search_actors(conn, name)
    if not matches:
        click.echo(f"No actor found matching '{name}'.")
        return None
    return pick_actor(matches, name)


def _print_chain(legs: list[list[dict]]) -> None:
    """Pretty-print one or more BFS path legs."""
    total_degrees = sum(len(leg) - 1 for leg in legs)
    multi = len(legs) > 1

    if multi:
        waypoints = [legs[0][0]["actor"]] + [leg[-1]["actor"] for leg in legs]
        header = " → ".join(waypoints)
        click.echo(f"\n{click.style(header, bold=True)}")
        degree_str = click.style(str(total_degrees), bold=True)
        click.echo(
            f"{degree_str} degree{'s' if total_degrees != 1 else ''} total"
            f" across {len(legs)} leg{'s' if len(legs) != 1 else ''}\n"
        )
    else:
        degrees = total_degrees
        click.echo(
            f"\nFound in {click.style(str(degrees), bold=True)} "
            f"degree{'s' if degrees != 1 else ''}:\n"
        )

    for i, leg in enumerate(legs):
        if multi:
            deg = len(leg) - 1
            label = (
                f"  Leg {i + 1}: "
                f"{leg[0]['actor']} → {leg[-1]['actor']}"
                f"  ({deg} degree{'s' if deg != 1 else ''})"
            )
            click.echo(click.style(label, fg="yellow"))

        for step in leg:
            actor_str = click.style(step["actor"], bold=True)
            if step["movie"]:
                movie_str = click.style(step["movie"], fg="cyan")
                click.echo(f"  {actor_str}")
                click.echo(f"    └─ {movie_str}")
            else:
                click.echo(f"  {actor_str}")

        click.echo()


@cli.command()
@click.argument("actors", nargs=-1)
@click.option(
    "--max-degrees",
    default=6,
    show_default=True,
    help="Maximum degrees of separation to search for each leg.",
)
@click.option(
    "--after-year",
    default=None,
    type=int,
    help="Only use films released after this year (e.g. --after-year 1980).",
)
@click.option(
    "--movies-only",
    is_flag=True,
    default=False,
    help="Only use theatrical movies (excludes TV movies, series, etc.).",
)
@click.option(
    "--min-rating",
    default=None,
    type=float,
    help="Minimum IMDB average rating for films used (e.g. --min-rating 7.0).",
)
@click.option(
    "--min-votes",
    default=None,
    type=int,
    help="Minimum IMDB vote count for films used (e.g. --min-votes 50000).",
)
def connect(actors: tuple[str, ...], max_degrees: int, after_year: int | None, movies_only: bool, min_rating: float | None, min_votes: int | None) -> None:
    """Find the shortest connection between two or more actors.

    Provide two or more names to chain them together via shared films.
    When fewer than two names are given you will be prompted interactively
    with live autocomplete; keep entering names to add waypoints, then press
    Enter on an empty line to start the search.

    \b
    Examples:
        actor-game connect                                         # fully interactive
        actor-game connect "Tom Hanks" "Kevin Bacon"               # two actors
        actor-game connect "Tom Hanks" "Kevin Bacon" "Meryl Streep" # chain of three
    """
    interactive = len(actors) < 2
    completer = ActorCompleter(DB_PATH) if interactive else None

    try:
        conn = open_db()
        resolved: list[dict] = []

        # Resolve any actors already supplied on the command line
        for name in actors:
            a = _resolve_actor_from_name(conn, name)
            if a is None:
                return
            resolved.append(a)

        if interactive:
            idx = len(resolved) + 1
            # First two are required
            while len(resolved) < 2:
                a = prompt_actor(f"Actor {idx}", completer, conn, optional=False)
                if a is None:
                    return
                resolved.append(a)
                idx += 1
            # Additional waypoints are optional — empty input starts the search
            while True:
                a = prompt_actor(
                    f"Actor {idx} (or Enter to search)", completer, conn, optional=True
                )
                if a is None:
                    break
                resolved.append(a)
                idx += 1

        names_str = " → ".join(a["name"] for a in resolved)
        notes = []
        if after_year:
            notes.append(f"from {after_year} onwards")
        if movies_only:
            notes.append("movies only")
        if min_rating:
            notes.append(f"rating ≥ {min_rating}")
        if min_votes:
            notes.append(f"votes ≥ {min_votes:,}")
        note = f" ({', '.join(notes)})" if notes else ""
        click.echo(f"\nSearching: {names_str}{note} ...")

        legs: list[list[dict]] = []
        for i in range(len(resolved) - 1):
            a, b = resolved[i], resolved[i + 1]
            path = bfs(conn, a["nconst"], b["nconst"], max_degrees, min_year=after_year, movies_only=movies_only, min_rating=min_rating, min_votes=min_votes)
            if path is None:
                click.echo(
                    f"No connection found between {a['name']} and {b['name']}"
                    f" within {max_degrees} degrees."
                )
                return
            legs.append(path)

        conn.close()
    finally:
        if completer:
            completer.close()

    _print_chain(legs)


@cli.command()
@click.argument("name")
def search(name: str) -> None:
    """Search for actors by name in the local database."""
    conn = open_db()
    matches = search_actors(conn, name)
    conn.close()
    if not matches:
        click.echo(f"No results for '{name}'.")
        return
    click.echo(f"Results for '{name}':")
    for m in matches:
        click.echo(f"  {m['name']}  ({m['nconst']})")


@cli.command()
def info() -> None:
    """Show database statistics."""
    if not DB_PATH.exists():
        click.echo("Database not found. Run `actor-game setup` first.")
        return
    conn = sqlite3.connect(DB_PATH)
    actors = conn.execute("SELECT COUNT(*) FROM actors").fetchone()[0]
    movies = conn.execute("SELECT COUNT(*) FROM movies").fetchone()[0]
    appearances = conn.execute("SELECT COUNT(*) FROM appearances").fetchone()[0]
    size_mb = DB_PATH.stat().st_size / 1024 / 1024
    conn.close()
    click.echo(f"Database: {DB_PATH}")
    click.echo(f"  Actors/actresses : {actors:>12,}")
    click.echo(f"  Titles           : {movies:>12,}")
    click.echo(f"  Appearances      : {appearances:>12,}")
    click.echo(f"  File size        : {size_mb:>11.1f} MB")


@cli.command()
@click.option("--host", default="127.0.0.1", show_default=True, help="Host to bind to.")
@click.option("--port", default=8000, show_default=True, help="Port to listen on.")
def serve(host: str, port: int) -> None:
    """Start the web UI server.

    Opens a browser-based UI at http://<host>:<port>.
    Run `actor-game setup` first if you haven't already.
    """
    try:
        import uvicorn
    except ImportError:
        click.echo("uvicorn is not installed. Run: uv add uvicorn[standard]", err=True)
        raise SystemExit(1)
    click.echo(f"Starting web UI at http://{host}:{port}")
    uvicorn.run("server:app", host=host, port=port, reload=False)


# ---------------------------------------------------------------------------
# Download helper
# ---------------------------------------------------------------------------

def _download(url: str, dest: Path) -> None:
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        with open(dest, "wb") as f, tqdm(
            total=total, unit="B", unit_scale=True, desc=f"  {dest.name}"
        ) as bar:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                f.write(chunk)
                bar.update(len(chunk))


if __name__ == "__main__":
    cli()
