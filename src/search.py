"""Actor search and interactive autocomplete prompt."""

import sqlite3
from pathlib import Path

import click
from prompt_toolkit import prompt as pt_prompt
from prompt_toolkit.completion import Completer, Completion


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
