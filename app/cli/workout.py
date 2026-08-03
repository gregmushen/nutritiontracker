"""workout CLI subcommands — talk to the workout tracker API."""
import json
import os
import re

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


def _post(path: str, body: dict) -> dict | list:
    r = httpx.post(f"{_base()}{path}", headers=_headers(), json=body, timeout=10)
    r.raise_for_status()
    return r.json()


def _parse_set(s: str) -> dict:
    """Parse shorthand like '135x8', '60kgx5', 'bwx12', '60s', 'plank 60s'."""
    s = s.strip()
    # timed: '60s' or 'plank 60s' (optional leading word stripped)
    m_timed = re.match(r"^(?:[a-zA-Z]+\s+)?(\d+)s$", s, re.IGNORECASE)
    if m_timed and "x" not in s:
        return {"duration_seconds": int(m_timed.group(1)), "reps": None}
    # weight x reps: '135x8', '60kgx5', 'bwx12'
    m = re.match(r"^(bw|(\d+(?:\.\d+)?)(kg|lb)?)x(\d+(?:\.\d+)?)$", s, re.IGNORECASE)
    if m:
        if m.group(1).lower() == "bw":
            return {"reps": float(m.group(4)), "set_type": "bodyweight"}
        weight = float(m.group(2))
        unit = (m.group(3) or "lb").lower()
        reps = float(m.group(4))
        return {"weight": weight, "weight_unit": unit, "reps": reps}
    raise click.BadParameter(f"Cannot parse set: '{s}'. Use '135x8', '60kgx5', 'bwx12', '60s'")


def _today_open_session() -> int | None:
    import datetime
    today = datetime.date.today().isoformat()
    sessions = _get("/workouts/sessions", start=today, end=today)
    open_sessions = [s for s in sessions if not s.get("ended_at")]
    return open_sessions[0]["id"] if open_sessions else None


@click.group()
def workout():
    """Workout tracking commands."""
    pass


@workout.command("start")
@click.option("--title", default=None)
@click.option("--date", default=None, help="Date (YYYY-MM-DD). Defaults to today.")
def start(title, date):
    """Start a new workout session."""
    import datetime
    body = {"date": date or datetime.date.today().isoformat()}
    if title:
        body["title"] = title
    session = _post("/workouts/sessions", body)
    click.echo(f"Session {session['id']} started — {session.get('title', session['date'])}")


@workout.command("today")
@click.option("--agent", is_flag=True, help="Output raw JSON")
def today(agent):
    """Show today's open workout session."""
    import datetime
    today_str = datetime.date.today().isoformat()
    data = _get("/workouts/sessions", start=today_str, end=today_str)
    if agent:
        click.echo(json.dumps(data))
    else:
        if not data:
            click.echo("No workout today yet. Use: workout start")
        else:
            for s in data:
                status = "open" if not s.get("ended_at") else "closed"
                click.echo(f"[{s['id']}] {s.get('title', s['date'])} ({status})")


@workout.command("add-set")
@click.option("--exercise", required=True)
@click.option("--session", "session_id", default=None, type=int,
              help="Session ID. Defaults to today's open session.")
@click.option("--weight", type=float, default=None)
@click.option("--lb", "unit", flag_value="lb", default=True)
@click.option("--kg", "unit", flag_value="kg")
@click.option("--reps", type=float, default=None)
@click.option("--type", "set_type", default="working")
def add_set(exercise, session_id, weight, unit, reps, set_type):
    """Log a single set."""
    ex_results = _get("/exercises/search", q=exercise, limit=1)
    if not ex_results:
        raise click.ClickException(f"Exercise not found: '{exercise}'")
    ex = ex_results[0]
    if session_id is None:
        session_id = _today_open_session()
        if session_id is None:
            raise click.ClickException("No open session today. Use: workout start")
    body = {"exercise_template_id": ex["id"], "set_type": set_type}
    if weight is not None:
        body["weight"] = weight
        body["weight_unit"] = unit
    if reps is not None:
        body["reps"] = reps
    result = _post(f"/workouts/sessions/{session_id}/sets", body)
    click.echo(
        f"Set logged: {ex['name']} "
        f"{result.get('weight', '')} {result.get('weight_unit', '')} "
        f"x {result.get('reps', '')}"
    )


@workout.command("add-bulk")
@click.option("--exercise", required=True)
@click.argument("sets_str")
@click.option("--session", "session_id", default=None, type=int)
def add_bulk(exercise, sets_str, session_id):
    """Log multiple sets. Example: workout add-bulk --exercise bench '135x8,155x5,165x3'"""
    if session_id is None:
        session_id = _today_open_session()
        if session_id is None:
            raise click.ClickException("No open session today. Use: workout start")
    sets = [_parse_set(s.strip()) for s in sets_str.split(",")]
    body = {"exercise_query": exercise, "sets": sets}
    results = _post(f"/workouts/sessions/{session_id}/sets/bulk", body)
    click.echo(f"Logged {len(results)} sets for {exercise}")


@workout.command("recent")
@click.option("--exercise", required=True)
@click.option("--limit", default=5)
@click.option("--agent", is_flag=True)
def recent(exercise, limit, agent):
    """Show recent sets for an exercise."""
    ex_results = _get("/exercises/search", q=exercise, limit=1)
    if not ex_results:
        raise click.ClickException(f"Exercise not found: '{exercise}'")
    data = _get("/workouts/recent", exercise_id=ex_results[0]["id"], limit=limit)
    if agent:
        click.echo(json.dumps(data))
    else:
        for s in data.get("sessions", []):
            top = s.get("top_set")
            top_str = (
                f"{top['weight']}{top.get('weight_unit','lb')} x {top['reps']}"
                if top else "—"
            )
            click.echo(f"  {s['date']} — top: {top_str} — vol: {s.get('volume', 0):.0f}")


@workout.command("progress")
@click.option("--exercise", required=True)
@click.option("--agent", is_flag=True)
def progress(exercise, agent):
    """Show e1RM progress for an exercise."""
    ex_results = _get("/exercises/search", q=exercise, limit=1)
    if not ex_results:
        raise click.ClickException(f"Exercise not found: '{exercise}'")
    data = _get("/workouts/progress", exercise_id=ex_results[0]["id"])
    if agent:
        click.echo(json.dumps(data))
    else:
        click.echo(
            f"Best e1RM: {data.get('best_e1rm', 0):.1f} lb  "
            f"Sessions: {data.get('session_count', 0)}"
        )
        for s in data.get("sessions", []):
            click.echo(
                f"  {s['date']} — e1RM: {s['estimated_1rm']:.1f}  vol: {s['volume']:.0f}"
            )


@workout.command("close")
@click.option("--session", "session_id", default=None, type=int)
@click.option("--notes", default=None)
@click.option("--energy", default=None, type=int)
@click.option("--soreness", default=None, type=int)
@click.option("--stress", default=None, type=int)
def close(session_id, notes, energy, soreness, stress):
    """Close out the current workout session."""
    if session_id is None:
        session_id = _today_open_session()
        if session_id is None:
            raise click.ClickException("No open session to close.")
    body = {}
    if notes:
        body["notes"] = notes
    if energy:
        body["energy_score"] = energy
    if soreness:
        body["soreness_score"] = soreness
    if stress:
        body["stress_score"] = stress
    result = _post(f"/workouts/sessions/{session_id}/close", body)
    click.echo(f"Session {result['id']} closed at {result['ended_at']}")
    if notes:
        click.echo(f"Notes: {notes}")
