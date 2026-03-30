"""
FastAPI backend for the Actor Connection Game web UI.
Run via:  uv run actor-game serve
Or directly:  uv run uvicorn server:app --reload
"""

import asyncio
import itertools
import os
import sqlite3
import time
from pathlib import Path
from typing import Union

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from actor_game import DB_PATH, _has_ratings, bfs, bfs_multi, open_db, search_actors


def _client_ip(request: Request) -> str:
    """Return the real client IP, respecting X-Forwarded-For from Cloud Run's proxy."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


limiter = Limiter(key_func=_client_ip)

app = FastAPI(title="Actor Connection Game")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS is only needed when the frontend dev server (port 5173) talks to the
# API server (port 8000/8080) on a different port — i.e. local development.
# In production both are served from the same Cloud Run origin, so CORS is a
# no-op there. Configure via ALLOWED_ORIGINS (comma-separated).
_origins = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()]
if _origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
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
    max_degrees: int = Field(6, ge=1, le=12)


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
    movie_tconst: str | None = None


class Leg(BaseModel):
    steps: list[PathStep]
    all_steps: list[list[PathStep]] = []
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


def _run_bfs_multi(conn, start_nconst, end_nconst, filters: Filters, forbidden: set | None = None) -> list[list[dict]]:
    return bfs_multi(
        conn,
        start_nconst,
        end_nconst,
        filters.max_degrees,
        k=5,
        min_year=filters.min_year,
        movies_only=filters.movies_only,
        min_rating=filters.min_rating,
        min_votes=filters.min_votes,
        forbidden=forbidden,
    )


def _steps_to_leg(all_paths: list[list[dict]]) -> Leg:
    first = all_paths[0]
    return Leg(
        steps=[PathStep(**s) for s in first],
        all_steps=[[PathStep(**s) for s in p] for p in all_paths],
        degrees=len(first) - 1,
    )


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

@app.get("/api/search")
@limiter.limit("60/minute")
async def search(request: Request, q: str = Query("", min_length=0), limit: int = Query(15, le=50)):
    """Return actors whose name matches the query string, sorted by popularity."""
    if not q or len(q) < 2:
        return []
    conn = open_db()
    try:
        MIN_VOTES = 50_000
        has_popularity = bool(conn.execute(
            "SELECT 1 FROM pragma_table_info('actors') WHERE name='max_votes'"
        ).fetchone())

        def _query(pattern, lim):
            if has_popularity:
                # All actors matching name, sorted by popularity descending.
                # MIN_VOTES is kept as a constant for easy threshold tuning but
                # no longer applied as a WHERE filter — less-known actors still
                # appear, just ranked below the famous ones.
                return conn.execute(
                    "SELECT nconst, name, max_votes, known_for FROM actors"
                    " WHERE name LIKE ?"
                    " ORDER BY max_votes DESC NULLS LAST LIMIT ?",
                    (pattern, lim),
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
@limiter.limit("10/minute")
async def connect(request: Request, req: ConnectRequest):
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
                    all_paths = _run_bfs_multi(conn, a["nconst"], b["nconst"], req.filters, forbidden=forbidden or None)
                    if not all_paths:
                        # No path found for this leg — skip this combo
                        legs = []
                        break
                    leg = _steps_to_leg(all_paths)
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


@app.get("/api/random-actors")
async def random_actors():
    """Return 2 random well-known actors (for page-load default)."""
    conn = open_db()
    try:
        has_popularity = bool(conn.execute(
            "SELECT 1 FROM pragma_table_info('actors') WHERE name='max_votes'"
        ).fetchone())
        if has_popularity:
            # Pick from actors with at least 500k votes so they're genuinely famous
            rows = conn.execute(
                "SELECT nconst, name FROM actors WHERE max_votes >= 500000"
                " ORDER BY RANDOM() LIMIT 2"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT nconst, name FROM actors ORDER BY RANDOM() LIMIT 2"
            ).fetchall()
        return [{"nconst": r["nconst"], "name": r["name"]} for r in rows]
    finally:
        conn.close()


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
