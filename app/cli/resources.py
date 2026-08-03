"""CLI groups for the remaining Nutrition Tracker API resources."""

from datetime import date
from typing import Any, Callable, TextIO

import click

from app.cli.client import CLIContext
from app.cli.nutrition import (
    ISO_DATE,
    _date_string,
    _echo_json,
    _json_object,
    _number,
    _today,
)


def _params(**values: Any) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value is not None}


def _output(
    context: CLIContext,
    data: Any,
    formatter: Callable[[dict[str, Any]], str],
    *,
    empty: str = "No results.",
) -> None:
    if context.json_output:
        _echo_json(data)
        return
    if isinstance(data, list):
        if not data:
            click.echo(empty)
            return
        for item in data:
            click.echo(formatter(item))
        return
    click.echo(formatter(data))


def _delete(
    context: CLIContext,
    path: str,
    label: str,
    item_id: int,
    yes: bool,
    *,
    params: dict[str, Any] | None = None,
) -> None:
    if not yes:
        click.confirm(f"Delete {label} {item_id}?", abort=True)
    context.client.request("DELETE", path, params=params)
    click.echo(f"Deleted {label} {item_id}.")


def _activity_line(row: dict[str, Any]) -> str:
    anomaly = " [anomaly]" if row["anomaly_flag"] else ""
    return f"{row['date']}: {row['steps']:,} steps ({row['source']}){anomaly}"


def _event_type_line(row: dict[str, Any]) -> str:
    unit = f" ({row['unit']})" if row.get("unit") else ""
    return f"[{row['id']}] {row['name']}{unit}"


def _event_line(row: dict[str, Any]) -> str:
    at = f" {row['at']}" if row.get("at") else ""
    value = ""
    if row.get("value") is not None:
        value = f" - {_number(row['value'])}"
        if row.get("unit"):
            value += f" {row['unit']}"
    return f"[{row['id']}] {row['date']}{at}: {row['event_type_name']}{value}"


def _inventory_line(row: dict[str, Any]) -> str:
    location = f" ({row['location']})" if row.get("location") else ""
    return f"[{row['id']}] {row['display_name']} - {row['status']}{location}"


def _meal_match_line(row: dict[str, Any]) -> str:
    missing = row["missing_required_ingredients"]
    suffix = f"; missing: {', '.join(missing)}" if missing else ""
    return f"[{row['meal_id']}] {row['meal_name']} - score {row['score']}{suffix}"


@click.group()
def activity() -> None:
    """View and import step activity."""


@activity.command("daily")
@click.argument("day", type=ISO_DATE, required=False, default=_today)
@click.pass_obj
def activity_daily(context: CLIContext, day: date) -> None:
    """Show activity for DAY (defaults to today)."""
    result = context.client.request(
        "GET",
        f"/activity/daily/{_date_string(day)}",
    )
    _output(context, result, _activity_line)


@activity.command("range")
@click.argument("start", type=ISO_DATE)
@click.argument("end", type=ISO_DATE)
@click.pass_obj
def activity_range(context: CLIContext, start: date, end: date) -> None:
    """Show activity from START through END."""
    if start > end:
        raise click.UsageError("START must not be after END")
    result = context.client.request(
        "GET",
        "/activity/range",
        params={"start": _date_string(start), "end": _date_string(end)},
    )
    _output(
        context,
        result,
        _activity_line,
        empty="No activity in this date range.",
    )


@activity.command("import-steps")
@click.option("--source", required=True)
@click.option("--observed-at", required=True)
@click.option("--period-start", required=True)
@click.option("--period-end", required=True)
@click.option("--steps", type=click.IntRange(min=0), required=True)
@click.option("--timezone", required=True)
@click.pass_obj
def import_steps(
    context: CLIContext,
    source: str,
    observed_at: str,
    period_start: str,
    period_end: str,
    steps: int,
    timezone: str,
) -> None:
    """Import a cumulative step observation."""
    result = context.client.request(
        "POST",
        "/imports/activity/steps",
        json={
            "source": source,
            "observed_at": observed_at,
            "period_start": period_start,
            "period_end": period_end,
            "steps_total_today": steps,
            "timezone": timezone,
        },
    )
    _echo_json(result)


@click.group()
def journal() -> None:
    """Create and inspect journal entries."""


@journal.command("add")
@click.argument("body")
@click.option("--date", "entry_date", type=ISO_DATE, default=_today)
@click.option("--tag", "tags", multiple=True)
@click.option("--mood", type=click.IntRange(1, 10))
@click.option("--stress", type=click.IntRange(1, 10))
@click.option("--sleep", type=click.IntRange(1, 10))
@click.pass_obj
def add_journal(
    context: CLIContext,
    body: str,
    entry_date: date,
    tags: tuple[str, ...],
    mood: int | None,
    stress: int | None,
    sleep: int | None,
) -> None:
    """Create a journal entry."""
    payload = {
        "date": _date_string(entry_date),
        "body": body,
        "tags": list(tags),
        **_params(
            mood_score=mood,
            stress_score=stress,
            sleep_quality=sleep,
        ),
    }
    result = context.client.request("POST", "/journal", json=payload)
    _echo_json(result)


@journal.command("get")
@click.argument("day", type=ISO_DATE, required=False, default=_today)
@click.pass_obj
def get_journal(context: CLIContext, day: date) -> None:
    """Show journal entries for DAY."""
    result = context.client.request("GET", f"/journal/{_date_string(day)}")
    _output(
        context,
        result,
        lambda row: f"[{row['id']}] {row['date']}: {row['body']}",
        empty="No journal entries for this date.",
    )


@journal.command("range")
@click.argument("start", type=ISO_DATE)
@click.argument("end", type=ISO_DATE)
@click.pass_obj
def journal_range(context: CLIContext, start: date, end: date) -> None:
    """Show journal entries from START through END."""
    if start > end:
        raise click.UsageError("START must not be after END")
    result = context.client.request(
        "GET",
        "/journal",
        params={"start": _date_string(start), "end": _date_string(end)},
    )
    _output(
        context,
        result,
        lambda row: f"[{row['id']}] {row['date']}: {row['body']}",
        empty="No journal entries in this date range.",
    )


@journal.command("update")
@click.argument("entry_id", type=int)
@click.option("--data", help="JournalEntryUpdate JSON object.")
@click.option("--data-file", type=click.File("r"), help="Read update JSON.")
@click.pass_obj
def update_journal(
    context: CLIContext,
    entry_id: int,
    data: str | None,
    data_file: TextIO | None,
) -> None:
    """Update a journal entry from JSON."""
    result = context.client.request(
        "PATCH",
        f"/journal/{entry_id}",
        json=_json_object(data, data_file),
    )
    _echo_json(result)


@journal.command("delete")
@click.argument("entry_id", type=int)
@click.option("--yes", is_flag=True)
@click.pass_obj
def delete_journal(context: CLIContext, entry_id: int, yes: bool) -> None:
    """Delete a journal entry."""
    _delete(context, f"/journal/{entry_id}", "journal entry", entry_id, yes)


@click.group()
def recipes() -> None:
    """Create and inspect recipes."""


@recipes.command("list")
@click.option("--limit", type=click.IntRange(1, 100), default=20)
@click.option("--offset", type=click.IntRange(min=0), default=0)
@click.pass_obj
def list_recipes(context: CLIContext, limit: int, offset: int) -> None:
    """List recipes."""
    result = context.client.request(
        "GET",
        "/recipes",
        params={"limit": limit, "offset": offset},
    )
    _output(
        context,
        result,
        lambda row: (
            f"[{row['id']}] {row['name']} - "
            f"{_number(row['servings'])} servings, "
            f"{_number(row['total_weight_g'])}g"
        ),
        empty="No recipes found.",
    )


@recipes.command("get")
@click.argument("recipe_id", type=int)
@click.pass_obj
def get_recipe(context: CLIContext, recipe_id: int) -> None:
    """Show a recipe."""
    result = context.client.request("GET", f"/recipes/{recipe_id}")
    _echo_json(result)


@recipes.command("create")
@click.option("--data", help="RecipeCreate JSON object.")
@click.option(
    "--data-file",
    type=click.File("r"),
    help="Read RecipeCreate JSON.",
)
@click.pass_obj
def create_recipe(
    context: CLIContext,
    data: str | None,
    data_file: TextIO | None,
) -> None:
    """Create a recipe from JSON."""
    result = context.client.request(
        "POST",
        "/recipes",
        json=_json_object(data, data_file),
    )
    _echo_json(result)


@recipes.command("update")
@click.argument("recipe_id", type=int)
@click.option("--data", help="RecipeUpdate JSON object.")
@click.option(
    "--data-file",
    type=click.File("r"),
    help="Read RecipeUpdate JSON.",
)
@click.pass_obj
def update_recipe(
    context: CLIContext,
    recipe_id: int,
    data: str | None,
    data_file: TextIO | None,
) -> None:
    """Update a recipe from JSON."""
    result = context.client.request(
        "PATCH",
        f"/recipes/{recipe_id}",
        json=_json_object(data, data_file),
    )
    _echo_json(result)


@recipes.command("delete")
@click.argument("recipe_id", type=int)
@click.option("--yes", is_flag=True)
@click.pass_obj
def delete_recipe(context: CLIContext, recipe_id: int, yes: bool) -> None:
    """Delete a recipe."""
    _delete(context, f"/recipes/{recipe_id}", "recipe", recipe_id, yes)


@click.group()
def events() -> None:
    """Define, log, and inspect events."""


@click.group("types")
def event_types() -> None:
    """Manage event types."""


@event_types.command("list")
@click.pass_obj
def list_event_types(context: CLIContext) -> None:
    """List event types."""
    result = context.client.request("GET", "/events/types")
    _output(
        context,
        result,
        _event_type_line,
        empty="No event types found.",
    )


@event_types.command("get")
@click.argument("type_id", type=int)
@click.pass_obj
def get_event_type(context: CLIContext, type_id: int) -> None:
    """Show an event type."""
    result = context.client.request("GET", f"/events/types/{type_id}")
    _echo_json(result)


@event_types.command("create")
@click.argument("name")
@click.option("--unit")
@click.option("--notes")
@click.pass_obj
def create_event_type(
    context: CLIContext,
    name: str,
    unit: str | None,
    notes: str | None,
) -> None:
    """Create an event type."""
    result = context.client.request(
        "POST",
        "/events/types",
        json={"name": name, **_params(unit=unit, notes=notes)},
    )
    _echo_json(result)


@event_types.command("update")
@click.argument("type_id", type=int)
@click.option("--data", help="EventTypeUpdate JSON object.")
@click.option("--data-file", type=click.File("r"), help="Read update JSON.")
@click.pass_obj
def update_event_type(
    context: CLIContext,
    type_id: int,
    data: str | None,
    data_file: TextIO | None,
) -> None:
    """Update an event type from JSON."""
    result = context.client.request(
        "PATCH",
        f"/events/types/{type_id}",
        json=_json_object(data, data_file),
    )
    _echo_json(result)


@event_types.command("delete")
@click.argument("type_id", type=int)
@click.option("--cascade", is_flag=True, help="Also delete events of this type.")
@click.option("--yes", is_flag=True)
@click.pass_obj
def delete_event_type(
    context: CLIContext,
    type_id: int,
    cascade: bool,
    yes: bool,
) -> None:
    """Delete an event type."""
    _delete(
        context,
        f"/events/types/{type_id}",
        "event type",
        type_id,
        yes,
        params={"cascade": str(cascade).lower()},
    )


events.add_command(event_types)


@events.command("list")
@click.option("--start", type=ISO_DATE)
@click.option("--end", type=ISO_DATE)
@click.option("--type", "event_type_id", type=int)
@click.option("--limit", type=click.IntRange(1, 500), default=100)
@click.option("--offset", type=click.IntRange(min=0), default=0)
@click.pass_obj
def list_events(
    context: CLIContext,
    start: date | None,
    end: date | None,
    event_type_id: int | None,
    limit: int,
    offset: int,
) -> None:
    """List events with optional filters."""
    if start and end and start > end:
        raise click.UsageError("--start must not be after --end")
    result = context.client.request(
        "GET",
        "/events",
        params=_params(
            start=_date_string(start) if start else None,
            end=_date_string(end) if end else None,
            event_type_id=event_type_id,
            limit=limit,
            offset=offset,
        ),
    )
    _output(context, result, _event_line, empty="No events found.")


@events.command("get")
@click.argument("event_id", type=int)
@click.pass_obj
def get_event(context: CLIContext, event_id: int) -> None:
    """Show an event."""
    result = context.client.request("GET", f"/events/{event_id}")
    _echo_json(result)


@events.command("add")
@click.argument("event_type_id", type=int)
@click.option("--date", "event_date", type=ISO_DATE, default=_today)
@click.option("--at")
@click.option("--value", type=float)
@click.option("--unit")
@click.option("--notes")
@click.pass_obj
def add_event(
    context: CLIContext,
    event_type_id: int,
    event_date: date,
    at: str | None,
    value: float | None,
    unit: str | None,
    notes: str | None,
) -> None:
    """Log an event."""
    result = context.client.request(
        "POST",
        "/events",
        json={
            "event_type_id": event_type_id,
            "date": _date_string(event_date),
            **_params(at=at, value=value, unit=unit, notes=notes),
        },
    )
    _echo_json(result)


@events.command("update")
@click.argument("event_id", type=int)
@click.option("--data", help="EventUpdate JSON object.")
@click.option("--data-file", type=click.File("r"), help="Read update JSON.")
@click.pass_obj
def update_event(
    context: CLIContext,
    event_id: int,
    data: str | None,
    data_file: TextIO | None,
) -> None:
    """Update an event from JSON."""
    result = context.client.request(
        "PATCH",
        f"/events/{event_id}",
        json=_json_object(data, data_file),
    )
    _echo_json(result)


@events.command("delete")
@click.argument("event_id", type=int)
@click.option("--yes", is_flag=True)
@click.pass_obj
def delete_event(context: CLIContext, event_id: int, yes: bool) -> None:
    """Delete an event."""
    _delete(context, f"/events/{event_id}", "event", event_id, yes)


@events.command("summary")
@click.option("--start", type=ISO_DATE)
@click.option("--end", type=ISO_DATE)
@click.pass_obj
def event_summary(
    context: CLIContext,
    start: date | None,
    end: date | None,
) -> None:
    """Summarize events by type."""
    result = context.client.request(
        "GET",
        "/events/summary",
        params=_params(
            start=_date_string(start) if start else None,
            end=_date_string(end) if end else None,
        ),
    )
    _output(
        context,
        result,
        lambda row: (
            f"{row['event_type_name']}: {row['count']} events, "
            f"total {_number(row['total_value'])} {row.get('unit') or ''}".rstrip()
        ),
        empty="No events found.",
    )


@click.group()
def kitchen() -> None:
    """Manage kitchen inventory, meals, and shopping."""


@click.group("inventory")
def inventory() -> None:
    """Manage kitchen inventory."""


@inventory.command("list")
@click.option("--status")
@click.option("--location")
@click.option("--category")
@click.option("--search", "query")
@click.pass_obj
def list_inventory(
    context: CLIContext,
    status: str | None,
    location: str | None,
    category: str | None,
    query: str | None,
) -> None:
    """List or search inventory."""
    result = context.client.request(
        "GET",
        "/kitchen/inventory",
        params=_params(
            status=status,
            location=location,
            category=category,
            q=query,
        ),
    )
    _output(
        context,
        result,
        _inventory_line,
        empty="No inventory items found.",
    )


@inventory.command("add")
@click.argument("name")
@click.option(
    "--status",
    type=click.Choice(["have", "use_soon", "maybe", "out", "staple"]),
    default="have",
)
@click.option(
    "--location",
    type=click.Choice(["fridge", "freezer", "pantry", "other"]),
)
@click.option("--category")
@click.option("--notes")
@click.pass_obj
def add_inventory(
    context: CLIContext,
    name: str,
    status: str,
    location: str | None,
    category: str | None,
    notes: str | None,
) -> None:
    """Create or update an inventory item."""
    result = context.client.request(
        "POST",
        "/kitchen/inventory",
        json={
            "name": name,
            "status": status,
            **_params(location=location, category=category, notes=notes),
        },
    )
    _echo_json(result)


@inventory.command("delete")
@click.argument("item_id", type=int)
@click.option("--yes", is_flag=True)
@click.pass_obj
def delete_inventory(context: CLIContext, item_id: int, yes: bool) -> None:
    """Delete an inventory item."""
    _delete(
        context,
        f"/kitchen/inventory/{item_id}",
        "inventory item",
        item_id,
        yes,
    )


kitchen.add_command(inventory)


@click.group("meals")
def meals() -> None:
    """Manage favorite meals."""


@meals.command("list")
@click.pass_obj
def list_meals(context: CLIContext) -> None:
    """List favorite meals."""
    result = context.client.request("GET", "/kitchen/meals")
    _output(
        context,
        result,
        lambda row: (
            f"[{row['id']}] {row['name']} - score {row['favorite_score']}, "
            f"made {row['times_made']} times"
        ),
        empty="No favorite meals found.",
    )


@meals.command("create")
@click.option("--data", help="FavoriteMealCreate JSON object.")
@click.option("--data-file", type=click.File("r"), help="Read meal JSON.")
@click.pass_obj
def create_meal(
    context: CLIContext,
    data: str | None,
    data_file: TextIO | None,
) -> None:
    """Create a favorite meal from JSON."""
    result = context.client.request(
        "POST",
        "/kitchen/meals",
        json=_json_object(data, data_file),
    )
    _echo_json(result)


@meals.command("made")
@click.argument("meal_id", type=int)
@click.pass_obj
def mark_meal_made(context: CLIContext, meal_id: int) -> None:
    """Mark a favorite meal as made."""
    result = context.client.request("POST", f"/kitchen/meals/{meal_id}/made")
    _echo_json(result)


kitchen.add_command(meals)


@kitchen.command("matches")
@click.option("--effort", type=click.Choice(["low", "medium", "high"]))
@click.option("--tag")
@click.pass_obj
def kitchen_matches(
    context: CLIContext,
    effort: str | None,
    tag: str | None,
) -> None:
    """Rank favorite meals against current inventory."""
    result = context.client.request(
        "POST",
        "/kitchen/matches",
        json=_params(effort=effort, tag=tag),
    )
    _output(
        context,
        result,
        _meal_match_line,
        empty="No matching meals found.",
    )


@click.group("shopping")
def shopping() -> None:
    """Manage the shopping list."""


@shopping.command("list")
@click.option("--checked/--unchecked", default=None)
@click.pass_obj
def list_shopping(context: CLIContext, checked: bool | None) -> None:
    """List shopping items."""
    checked_param = str(checked).lower() if checked is not None else None
    result = context.client.request(
        "GET",
        "/kitchen/shopping-list",
        params=_params(checked=checked_param),
    )
    _output(
        context,
        result,
        lambda row: (
            f"[{row['id']}] {'[x]' if row['checked'] else '[ ]'} "
            f"{row['display_name']} ({row['source']})"
        ),
        empty="No shopping items found.",
    )


@shopping.command("add")
@click.argument("name")
@click.option(
    "--source",
    type=click.Choice(
        ["manual", "meal_plan", "inventory", "staple_refresh", "suggestion"]
    ),
    default="manual",
)
@click.option("--meal-id", "meal_ids", type=int, multiple=True)
@click.option("--notes")
@click.pass_obj
def add_shopping(
    context: CLIContext,
    name: str,
    source: str,
    meal_ids: tuple[int, ...],
    notes: str | None,
) -> None:
    """Add a shopping-list item."""
    result = context.client.request(
        "POST",
        "/kitchen/shopping-list",
        json={
            "name": name,
            "source": source,
            "linked_meal_ids": list(meal_ids),
            **_params(notes=notes),
        },
    )
    _echo_json(result)


@shopping.command("generate")
@click.argument("meal_ids", type=int, nargs=-1, required=True)
@click.pass_obj
def generate_shopping(context: CLIContext, meal_ids: tuple[int, ...]) -> None:
    """Generate shopping items for one or more MEAL_IDS."""
    result = context.client.request(
        "POST",
        "/kitchen/shopping-list/generate",
        json={"meal_ids": list(meal_ids)},
    )
    _echo_json(result)


@shopping.command("check")
@click.argument("item_id", type=int)
@click.pass_obj
def check_shopping(context: CLIContext, item_id: int) -> None:
    """Mark a shopping item checked."""
    result = context.client.request(
        "PATCH",
        f"/kitchen/shopping-list/{item_id}",
        json={"checked": True},
    )
    _echo_json(result)


@shopping.command("uncheck")
@click.argument("item_id", type=int)
@click.pass_obj
def uncheck_shopping(context: CLIContext, item_id: int) -> None:
    """Mark a shopping item unchecked."""
    result = context.client.request(
        "PATCH",
        f"/kitchen/shopping-list/{item_id}",
        json={"checked": False},
    )
    _echo_json(result)


kitchen.add_command(shopping)


@click.group()
def users() -> None:
    """Inspect and administer users."""


@users.command("me")
@click.pass_obj
def current_user(context: CLIContext) -> None:
    """Show the authenticated user."""
    result = context.client.request("GET", "/users/me")
    _echo_json(result)


@users.command("list")
@click.pass_obj
def list_users(context: CLIContext) -> None:
    """List users (admin only)."""
    result = context.client.request("GET", "/users")
    _output(
        context,
        result,
        lambda row: f"[{row['id']}] {row['name']}",
        empty="No users found.",
    )


@users.command("create")
@click.argument("name")
@click.pass_obj
def create_user(context: CLIContext, name: str) -> None:
    """Create a user and print its new token (admin only)."""
    result = context.client.request("POST", "/users", json={"name": name})
    _echo_json(result)


@users.command("rotate-token")
@click.argument("user_id", type=int)
@click.confirmation_option(
    prompt="Rotate this user token? The old token will stop working"
)
@click.pass_obj
def rotate_user_token(context: CLIContext, user_id: int) -> None:
    """Rotate a user token and print the replacement (admin only)."""
    result = context.client.request("POST", f"/users/{user_id}/token")
    _echo_json(result)
