"""
FastAPI backend for the Actor Connection Game web UI.
Run via:  uv run actor-game serve
Or directly:  uv run uvicorn server:app --reload
"""

import asyncio
import itertools
import sqlite3
import time
from pathlib import Path
from typing import Union

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from actor_game import DB_PATH, _has_ratings, bfs, open_db, search_actors

app = FastAPI(title="Actor Connection Game")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class ActorRef(BaseModel):
    nconst: str
    name: str | None = None


class Filters(BaseModel):
    movies_only: bool = False
    min_year: int | None = None
    min_rating: float | None = None
    min_votes: int | None = None
    max_degrees: int = 6


class ConnectRequest(BaseModel):
    # Each element is either a single actor or a list of alternatives (branch)
    actors: list[Union[ActorRef, list[ActorRef]]]
    filters: Filters = Filters()


class PathStep(BaseModel):
    actor: str
    nconst: str
    movie: str | None
    movie_year: int | None
    movie_type: str | None
    movie_rating: float | None


class Leg(BaseModel):
    steps: list[PathStep]
    degrees: int


class PathResult(BaseModel):
    combo_label: str
    legs: list[Leg]
    total_degrees: int


class ConnectResponse(BaseModel):
    paths: list[PathResult]
    elapsed_ms: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve(conn: sqlite3.Connection, ref: ActorRef) -> dict | None:
    row = conn.execute(
        "SELECT nconst, name FROM actors WHERE nconst=?", (ref.nconst,)
    ).fetchone()
    return dict(row) if row else None


def _run_bfs(conn, start_nconst, end_nconst, filters: Filters, forbidden: set | None = None):
    return bfs(
        conn,
        start_nconst,
        end_nconst,
        filters.max_degrees,
        min_year=filters.min_year,
        movies_only=filters.movies_only,
        min_rating=filters.min_rating,
        min_votes=filters.min_votes,
        forbidden=forbidden,
    )


def _steps_to_leg(steps: list[dict]) -> Leg:
    return Leg(
        steps=[PathStep(**s) for s in steps],
        degrees=len(steps) - 1,
    )


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

@app.get("/api/search")
async def search(q: str = Query("", min_length=0), limit: int = Query(15, le=50)):
    """Return actors whose name matches the query string, sorted by popularity."""
    if not q or len(q) < 2:
        return []
    conn = open_db()
    try:
        has_ratings = _has_ratings(conn)
        MIN_VOTES = 50_000

        def _query(pattern, lim):
            if has_ratings:
                return conn.execute(
                    """
                    SELECT a.nconst, a.name, MAX(r.num_votes) AS max_votes,
                           (SELECT m2.title
                            FROM movies m2
                            JOIN appearances ap2 ON m2.tconst = ap2.tconst
                            JOIN ratings r2 ON m2.tconst = r2.tconst
                            WHERE ap2.nconst = a.nconst AND r2.num_votes >= ?
                            ORDER BY r2.num_votes DESC LIMIT 1) AS known_for
                    FROM actors a
                    JOIN appearances ap ON a.nconst = ap.nconst
                    JOIN ratings r ON ap.tconst = r.tconst
                    WHERE a.name LIKE ? AND r.num_votes >= ?
                    GROUP BY a.nconst, a.name
                    ORDER BY max_votes DESC
                    LIMIT ?
                    """,
                    (MIN_VOTES, pattern, MIN_VOTES, lim),
                ).fetchall()
            else:
                return conn.execute(
                    "SELECT nconst, name, NULL as max_votes, NULL as known_for"
                    " FROM actors WHERE name LIKE ? ORDER BY name LIMIT ?",
                    (pattern, lim),
                ).fetchall()

        rows = _query(q + "%", limit)
        if len(rows) < 5:
            seen = {r["nconst"] for r in rows}
            extra = [r for r in _query(f"%{q}%", limit) if r["nconst"] not in seen]
            rows = list(rows) + extra[: limit - len(rows)]

        return [
            {
                "nconst": r["nconst"],
                "name": r["name"],
                "known_for": r["known_for"] if r["known_for"] else None,
            }
            for r in rows
        ][:limit]
    finally:
        conn.close()


@app.post("/api/connect", response_model=ConnectResponse)
async def connect(req: ConnectRequest):
    """Find the shortest actor connection path(s)."""
    if len(req.actors) < 2:
        raise HTTPException(400, "Need at least 2 actors")

    # Normalise each slot to a list of ActorRef
    slots: list[list[ActorRef]] = []
    for slot in req.actors:
        if isinstance(slot, list):
            slots.append(slot)
        else:
            slots.append([slot])

    # Build all branch combinations (cap at 12)
    combos = list(itertools.product(*slots))
    if len(combos) > 12:
        raise HTTPException(400, f"Too many branch combinations ({len(combos)}); max 12")

    t0 = time.monotonic()

    def _compute():
        conn = open_db()
        results: list[PathResult] = []
        try:
            for combo in combos:
                # Verify all actors exist
                actors_resolved = []
                for ref in combo:
                    a = _resolve(conn, ref)
                    if a is None:
                        raise HTTPException(404, f"Actor not found: {ref.nconst}")
                    actors_resolved.append(a)

                label = " → ".join(a["name"] for a in actors_resolved)
                legs: list[Leg] = []
                total = 0

                # All endpoint nconsts in this combo — used to prevent node-revisiting
                all_nconsts = {a["nconst"] for a in actors_resolved}

                for i in range(len(actors_resolved) - 1):
                    a, b = actors_resolved[i], actors_resolved[i + 1]
                    # Forbid every combo actor except this leg's own start and end
                    forbidden = all_nconsts - {a["nconst"], b["nconst"]}
                    steps = _run_bfs(conn, a["nconst"], b["nconst"], req.filters, forbidden=forbidden or None)
                    if steps is None:
                        # No path found for this leg — skip this combo
                        legs = []
                        break
                    leg = _steps_to_leg(steps)
                    legs.append(leg)
                    total += leg.degrees

                if legs:
                    results.append(PathResult(
                        combo_label=label,
                        legs=legs,
                        total_degrees=total,
                    ))
        finally:
            conn.close()
        return results

    loop = asyncio.get_event_loop()
    paths = await loop.run_in_executor(None, _compute)

    elapsed = int((time.monotonic() - t0) * 1000)
    return ConnectResponse(paths=paths, elapsed_ms=elapsed)


@app.get("/api/info")
async def info():
    """Return database statistics."""
    if not DB_PATH.exists():
        raise HTTPException(503, "Database not found. Run `actor-game setup` first.")
    conn = sqlite3.connect(DB_PATH)
    try:
        actors = conn.execute("SELECT COUNT(*) FROM actors").fetchone()[0]
        movies = conn.execute("SELECT COUNT(*) FROM movies").fetchone()[0]
        appearances = conn.execute("SELECT COUNT(*) FROM appearances").fetchone()[0]
        has_ratings = bool(conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='ratings'"
        ).fetchone())
        size_mb = round(DB_PATH.stat().st_size / 1024 / 1024, 1)
        return {
            "actors": actors,
            "movies": movies,
            "appearances": appearances,
            "has_ratings": has_ratings,
            "size_mb": size_mb,
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Static frontend (production build)
# ---------------------------------------------------------------------------

_dist = Path(__file__).parent / "frontend" / "dist"
if _dist.exists():
    app.mount("/", StaticFiles(directory=str(_dist), html=True), name="static")
