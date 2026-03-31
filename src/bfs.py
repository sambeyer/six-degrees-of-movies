"""Bidirectional BFS path-finding between actors through shared movies."""

import sqlite3
from collections import deque

from db import _has_ratings


def _fetch_actor_movies(
    conn: sqlite3.Connection,
    nconst: str,
    ratings_available: bool,
    min_year: int | None,
    movies_only: bool,
    min_rating: float | None,
    min_votes: int | None,
) -> list[str]:
    """Return list of tconsts for movies this actor appeared in, respecting filters."""
    if min_year or movies_only or (ratings_available and (min_rating or min_votes)):
        conditions = ["a.nconst=?"]
        params: list = [nconst]
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
        rows = conn.execute(
            f"SELECT a.tconst FROM appearances a {joins} WHERE {where}", params
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT tconst FROM appearances WHERE nconst=?", (nconst,)
        ).fetchall()
    return [r[0] for r in rows]


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
        return [{"actor": name, "nconst": start, "movie": None, "movie_year": None, "movie_type": None, "movie_rating": None, "movie_tconst": None}]

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
            path.append({"actor": lookup_actor(nconst), "nconst": nconst, "movie": None, "movie_year": None, "movie_type": None, "movie_rating": None, "movie_tconst": None})
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
            path.append({"actor": lookup_actor(nconst), "nconst": nconst, "movie_tconst": via_tconst, **detail})

    return path


def bfs_multi(
    conn: sqlite3.Connection,
    start: str,
    end: str,
    max_depth: int,
    k: int = 5,
    min_year: int | None = None,
    movies_only: bool = False,
    min_rating: float | None = None,
    min_votes: int | None = None,
    forbidden: set[str] | None = None,
) -> list[list[dict]]:
    """
    Find up to k shortest paths from start to end, all of the minimum degree length.
    Returns a list of paths (each path is a list of step dicts matching bfs() output).
    """
    ratings_available = _has_ratings(conn)
    if not ratings_available:
        min_rating = None
        min_votes = None

    # Step 1: find the minimum distance via the existing bidirectional BFS
    first = bfs(conn, start, end, max_depth, min_year, movies_only, min_rating, min_votes, forbidden)
    if first is None:
        return []
    min_hops = len(first) - 1
    if min_hops == 0:
        return [first]

    # Cache movies and co-actors to avoid redundant DB queries
    movie_cache: dict[str, list[str]] = {}
    coactor_cache: dict[str, list[str]] = {}

    def get_movies(nconst: str) -> list[str]:
        if nconst not in movie_cache:
            movie_cache[nconst] = _fetch_actor_movies(
                conn, nconst, ratings_available, min_year, movies_only, min_rating, min_votes
            )
        return movie_cache[nconst]

    def get_coactors(tconst: str) -> list[str]:
        if tconst not in coactor_cache:
            rows = conn.execute(
                "SELECT nconst FROM appearances WHERE tconst=?", (tconst,)
            ).fetchall()
            coactor_cache[tconst] = [r[0] for r in rows]
        return coactor_cache[tconst]

    # Steps 2+3: forward and backward BFS to compute distance maps.
    # Cap node count so popular actors don't cause exponential blowup.
    # 2000 nodes is ample to find 5 diverse paths even for well-connected actors.
    MAX_BFS_NODES = 2_000

    # Seed forward map from the first path so those nodes are free.
    dist_fwd: dict[str, int] = {start: 0}
    for i, step in enumerate(first):
        dist_fwd[step["nconst"]] = i

    # Seed backward map from the first path
    dist_bwd: dict[str, int] = {end: 0}
    for i, step in enumerate(reversed(first)):
        dist_bwd[step["nconst"]] = i

    # Continue forward BFS
    fwd_frontier: deque[str] = deque(
        n for n, d in dist_fwd.items() if d < min_hops
    )
    while fwd_frontier and len(dist_fwd) < MAX_BFS_NODES:
        cur = fwd_frontier.popleft()
        d = dist_fwd[cur]
        if d >= min_hops:
            continue
        for tconst in get_movies(cur):
            for nconst in get_coactors(tconst):
                if nconst != cur and nconst not in dist_fwd and (forbidden is None or nconst not in forbidden):
                    dist_fwd[nconst] = d + 1
                    fwd_frontier.append(nconst)
                    if len(dist_fwd) >= MAX_BFS_NODES:
                        break
            if len(dist_fwd) >= MAX_BFS_NODES:
                break

    # Continue backward BFS
    bwd_frontier: deque[str] = deque(
        n for n, d in dist_bwd.items() if d < min_hops
    )
    while bwd_frontier and len(dist_bwd) < MAX_BFS_NODES:
        cur = bwd_frontier.popleft()
        d = dist_bwd[cur]
        if d >= min_hops:
            continue
        for tconst in get_movies(cur):
            for nconst in get_coactors(tconst):
                if nconst != cur and nconst not in dist_bwd and (forbidden is None or nconst not in forbidden):
                    dist_bwd[nconst] = d + 1
                    bwd_frontier.append(nconst)
                    if len(dist_bwd) >= MAX_BFS_NODES:
                        break
            if len(dist_bwd) >= MAX_BFS_NODES:
                break

    # Step 4: build the DAG of edges that lie on any shortest path
    # An edge actor→(movie)→co_actor is on a shortest path iff:
    #   dist_fwd[actor] + 1 + dist_bwd[co_actor] == min_hops
    # Cap edges per actor so the DFS terminates quickly for popular actors.
    MAX_EDGES_PER_ACTOR = k * 6
    succ: dict[str, list[tuple[str, str]]] = {}  # nconst -> [(next_nconst, via_tconst)]
    for actor, d in dist_fwd.items():
        if d >= min_hops:
            continue
        if d + dist_bwd.get(actor, 10 ** 9) != min_hops:
            continue
        seen_edges: set[tuple[str, str]] = set()
        nexts: list[tuple[str, str]] = []
        for tconst in get_movies(actor):
            for co in get_coactors(tconst):
                if co == actor:
                    continue
                if forbidden is not None and co in forbidden:
                    continue
                if d + 1 + dist_bwd.get(co, 10 ** 9) == min_hops:
                    edge = (co, tconst)
                    if edge not in seen_edges:
                        seen_edges.add(edge)
                        nexts.append(edge)
                        if len(nexts) >= MAX_EDGES_PER_ACTOR:
                            break
            if len(nexts) >= MAX_EDGES_PER_ACTOR:
                break
        if nexts:
            succ[actor] = nexts

    # Step 5: DFS to enumerate up to k paths
    has_ratings_tbl = _has_ratings(conn)
    actor_name_cache: dict[str, str] = {}
    movie_detail_cache: dict[str, dict] = {}

    def lookup_actor(nconst: str) -> str:
        if nconst not in actor_name_cache:
            row = conn.execute("SELECT name FROM actors WHERE nconst=?", (nconst,)).fetchone()
            actor_name_cache[nconst] = row["name"] if row else nconst
        return actor_name_cache[nconst]

    def lookup_detail(tconst: str) -> dict:
        if tconst not in movie_detail_cache:
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
                movie_detail_cache[tconst] = {"movie": tconst, "movie_year": None, "movie_type": None, "movie_rating": None}
            else:
                title = f"{row['title']} ({row['year']})" if row["year"] else row["title"]
                movie_detail_cache[tconst] = {
                    "movie": title,
                    "movie_year": int(row["year"]) if row["year"] and row["year"].isdigit() else None,
                    "movie_type": row["type"],
                    "movie_rating": row["avg_rating"],
                }
        return movie_detail_cache[tconst]

    results: list[list[dict]] = []

    def dfs(actor: str, path_actors: list[str], path_tconsts: list[str]) -> None:
        if len(results) >= k:
            return
        if actor == end:
            path: list[dict] = []
            for i, nconst in enumerate(path_actors):
                if i == 0:
                    path.append({"actor": lookup_actor(nconst), "nconst": nconst,
                                 "movie": None, "movie_year": None, "movie_type": None,
                                 "movie_rating": None, "movie_tconst": None})
                else:
                    t = path_tconsts[i - 1]
                    path.append({"actor": lookup_actor(nconst), "nconst": nconst,
                                 "movie_tconst": t, **lookup_detail(t)})
            results.append(path)
            return
        for (next_actor, via_movie) in succ.get(actor, []):
            if len(results) >= k:
                return
            dfs(next_actor, path_actors + [next_actor], path_tconsts + [via_movie])

    dfs(start, [start], [])
    return results if results else [first]
