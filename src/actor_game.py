#!/usr/bin/env python3
"""
Actor Connection Game
Find the shortest path between two actors via shared movies.

Uses IMDB's free datasets, downloaded and stored locally in a SQLite database.
Run `actor-game setup` first to download the data (~1GB download, ~2GB on disk).
"""

import sqlite3
from pathlib import Path

import click
import requests
from tqdm import tqdm

from bfs import bfs, bfs_multi  # noqa: F401 — re-exported for server.py
from db import (
    ALL_TITLE_TYPES,
    DB_PATH,
    DATA_DIR,
    IMDB_URLS,
    MOVIE_ONLY_TYPES,
    _has_ratings,  # noqa: F401 — re-exported for server.py
    build_database,
    open_db,  # noqa: F401 — re-exported for server.py
)
from search import (
    ActorCompleter,
    pick_actor,
    prompt_actor,
    search_actors,  # noqa: F401 — re-exported for server.py
)


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


# ---------------------------------------------------------------------------
# CLI helpers
# ---------------------------------------------------------------------------

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

    if DB_PATH.exists() and force:
        click.echo("\nForce-rebuilding database from scratch ...")
        DB_PATH.unlink()

    title_types = MOVIE_ONLY_TYPES if movies_only else ALL_TITLE_TYPES
    click.echo(
        f"\nBuilding database (title types: {', '.join(sorted(title_types))}) ..."
    )
    build_database(DATA_DIR, DB_PATH, title_types)
    click.echo(f"\nAll done. Database saved to {DB_PATH}")


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


if __name__ == "__main__":
    cli()
