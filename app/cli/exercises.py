"""exercises CLI subcommands — search the workout tracker exercise library."""
import os

import click
import httpx

WT_BASE = os.environ.get("WT_BASE_URL", "")
WT_TOKEN = os.environ.get("WT_BEARER_TOKEN", "")


def _base() -> str:
    if not WT_BASE:
        raise click.ClickException(
            "WT_BASE_URL is not set. Point it at your workout tracker, e.g. "
            "export WT_BASE_URL=https://workouts.example.com"
        )
    return WT_BASE.rstrip("/")


def _headers() -> dict:
    return {"Authorization": f"Bearer {WT_TOKEN}"}


def _get(path: str, **params) -> dict | list:
    r = httpx.get(f"{_base()}{path}", headers=_headers(), params=params, timeout=10)
    r.raise_for_status()
    return r.json()


@click.group()
def exercises():
    """Exercise library commands."""
    pass


@exercises.command("search")
@click.argument("query")
@click.option("--limit", default=5, show_default=True)
def search(query, limit):
    """Search exercises by name, alias, or muscle group."""
    results = _get("/exercises/search", q=query, limit=limit)
    if not results:
        click.echo(f"No exercises found for '{query}'")
        return
    for ex in results:
        muscles = ", ".join(ex.get("primary_muscles") or [])
        click.echo(f"[{ex['id']}] {ex['name']}  ({ex.get('equipment', '—')}){f'  — {muscles}' if muscles else ''}")
