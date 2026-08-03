"""Commands for the Nutrition Tracker API."""

import json
from datetime import date, datetime
from typing import Any, TextIO

import click

from app.cli.client import CLIContext

MEALS = ["breakfast", "lunch", "dinner", "snack"]
POUNDS_PER_KILOGRAM = 2.2046226218


class ISODate(click.ParamType):
    name = "date"

    def convert(self, value, param, ctx):
        if isinstance(value, date):
            return value
        try:
            return date.fromisoformat(value)
        except (TypeError, ValueError):
            self.fail(f"{value!r} must be a date in YYYY-MM-DD format", param, ctx)


ISO_DATE = ISODate()


def _today() -> str:
    return datetime.now().astimezone().date().isoformat()


def _echo_json(data: Any) -> None:
    click.echo(json.dumps(data, indent=2, sort_keys=True))


def _number(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:,.1f}".rstrip("0").rstrip(".")


def _macro_summary(nutrients: dict[str, Any]) -> str:
    calories = _number(nutrients.get("calories_kcal"))
    protein = _number(nutrients.get("protein_g"))
    carbs = _number(nutrients.get("carbs_g"))
    fat = _number(nutrients.get("fat_g"))
    return f"{calories} kcal | P {protein}g C {carbs}g F {fat}g"


def _date_string(value: date) -> str:
    return value.isoformat()


def _query_params(values: tuple[str, ...]) -> list[tuple[str, str]]:
    params = []
    for value in values:
        key, separator, item = value.partition("=")
        if not separator or not key:
            raise click.BadParameter(
                f"{value!r} must use KEY=VALUE syntax",
                param_hint="'--param'",
            )
        params.append((key, item))
    return params


def _json_object(
    data: str | None,
    data_file: TextIO | None,
    *,
    required: bool = True,
) -> dict[str, Any] | None:
    if data is not None and data_file is not None:
        raise click.UsageError("--data and --data-file cannot be combined")
    if data is None and data_file is None:
        if required:
            raise click.UsageError("Provide --data or --data-file")
        return None
    raw = data if data is not None else data_file.read()
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise click.BadParameter(
            f"invalid JSON: {exc.msg}",
            param_hint="'--data/--data-file'",
        ) from exc
    if not isinstance(value, dict):
        raise click.BadParameter(
            "must contain a JSON object",
            param_hint="'--data/--data-file'",
        )
    return value


@click.command()
@click.pass_obj
def health(context: CLIContext) -> None:
    """Check whether the Nutrition Tracker API is available."""
    data = context.client.request("GET", "/health")
    if context.json_output:
        _echo_json(data)
        return
    click.echo(f"Nutrition Tracker {data['version']}: {data['status']}")


@click.command()
@click.argument("path")
@click.option(
    "-p",
    "--param",
    "params",
    multiple=True,
    metavar="KEY=VALUE",
    help="Query parameter; repeat for multiple or repeated values.",
)
@click.pass_obj
def query(context: CLIContext, path: str, params: tuple[str, ...]) -> None:
    """GET raw JSON from a read-only API PATH."""
    if not path.startswith("/") or path.startswith("//"):
        raise click.BadParameter(
            "must start with one /, for example /events",
            param_hint="'PATH'",
        )
    if "?" in path:
        raise click.BadParameter(
            "must not contain a query string; use --param KEY=VALUE",
            param_hint="'PATH'",
        )
    data = context.client.request("GET", path, params=_query_params(params))
    _echo_json(data)


@click.command("request")
@click.argument(
    "method",
    type=click.Choice(["GET", "POST", "PATCH", "DELETE"], case_sensitive=False),
)
@click.argument("path")
@click.option(
    "-p",
    "--param",
    "params",
    multiple=True,
    metavar="KEY=VALUE",
    help="Query parameter; repeat for multiple or repeated values.",
)
@click.option("--data", help="JSON request object.")
@click.option(
    "--data-file",
    type=click.File("r"),
    help="Read the JSON request object from a file, or - for stdin.",
)
@click.pass_obj
def api_request(
    context: CLIContext,
    method: str,
    path: str,
    params: tuple[str, ...],
    data: str | None,
    data_file: TextIO | None,
) -> None:
    """Call any API endpoint with an authenticated HTTP METHOD."""
    if not path.startswith("/") or path.startswith("//"):
        raise click.BadParameter(
            "must start with one /, for example /events",
            param_hint="'PATH'",
        )
    if "?" in path:
        raise click.BadParameter(
            "must not contain a query string; use --param KEY=VALUE",
            param_hint="'PATH'",
        )
    body = _json_object(data, data_file, required=False)
    result = context.client.request(
        method.upper(),
        path,
        params=_query_params(params),
        json=body,
    )
    _echo_json({"status": "ok"} if result is None else result)


@click.group()
def foods() -> None:
    """Search and inspect the food catalog."""


@foods.command("search")
@click.argument("query")
@click.option("--source", default="all", show_default=True)
@click.option("--limit", type=click.IntRange(1, 100), default=10, show_default=True)
@click.option("--offset", type=click.IntRange(min=0), default=0, show_default=True)
@click.pass_obj
def search_foods(
    context: CLIContext,
    query: str,
    source: str,
    limit: int,
    offset: int,
) -> None:
    """Search foods by name or brand."""
    data = context.client.request(
        "GET",
        "/foods/search",
        params={"q": query, "source": source, "limit": limit, "offset": offset},
    )
    if context.json_output:
        _echo_json(data)
        return
    if not data:
        click.echo(f"No foods found for {query!r}.")
        return
    for food in data:
        brand = f" - {food['brand']}" if food.get("brand") else ""
        click.echo(
            f"[{food['id']}] {food['name']}{brand} ({food['source']}) | "
            f"{_macro_summary(food)} / 100g"
        )


@foods.command("get")
@click.argument("food_id", type=int)
@click.pass_obj
def get_food(context: CLIContext, food_id: int) -> None:
    """Show one food by ID."""
    food = context.client.request("GET", f"/foods/{food_id}")
    if context.json_output:
        _echo_json(food)
        return
    brand = f" - {food['brand']}" if food.get("brand") else ""
    click.echo(f"[{food['id']}] {food['name']}{brand}")
    click.echo(f"Source: {food['source']}")
    click.echo(f"Per 100g: {_macro_summary(food)}")
    if food.get("serving_quantity") and food.get("serving_unit"):
        click.echo(
            f"Serving: {_number(food['serving_quantity'])} {food['serving_unit']}"
        )


@foods.command("barcode")
@click.argument("barcode")
@click.pass_obj
def barcode(context: CLIContext, barcode: str) -> None:
    """Look up a food by UPC or EAN barcode."""
    food = context.client.request("GET", f"/foods/barcode/{barcode}")
    if context.json_output:
        _echo_json(food)
        return
    click.echo(
        f"[{food['id']}] {food['name']} ({food['source']}) | "
        f"{_macro_summary(food)} / 100g"
    )


@foods.command("sources")
@click.pass_obj
def food_sources(context: CLIContext) -> None:
    """List catalog data sources."""
    data = context.client.request("GET", "/foods/sources")
    if context.json_output:
        _echo_json(data)
        return
    for source in data:
        click.echo(
            f"{source['code']}: {source['label']} "
            f"(tier {source['tier']}, {source['food_count']:,} foods)"
        )


@foods.command("create")
@click.option("--data", help="FoodCreate JSON object.")
@click.option("--data-file", type=click.File("r"), help="Read FoodCreate JSON.")
@click.pass_obj
def create_food(
    context: CLIContext,
    data: str | None,
    data_file: TextIO | None,
) -> None:
    """Create a custom food from JSON."""
    result = context.client.request(
        "POST",
        "/foods",
        json=_json_object(data, data_file),
    )
    _echo_json(result)


@foods.command("update")
@click.argument("food_id", type=int)
@click.option("--data", help="FoodUpdate JSON object.")
@click.option("--data-file", type=click.File("r"), help="Read FoodUpdate JSON.")
@click.pass_obj
def update_food(
    context: CLIContext,
    food_id: int,
    data: str | None,
    data_file: TextIO | None,
) -> None:
    """Update a custom food from JSON."""
    result = context.client.request(
        "PATCH",
        f"/foods/{food_id}",
        json=_json_object(data, data_file),
    )
    _echo_json(result)


@foods.command("delete")
@click.argument("food_id", type=int)
@click.option("--yes", is_flag=True, help="Delete without confirmation.")
@click.pass_obj
def delete_food(context: CLIContext, food_id: int, yes: bool) -> None:
    """Delete a custom food."""
    if not yes:
        click.confirm(f"Delete custom food {food_id}?", abort=True)
    context.client.request("DELETE", f"/foods/{food_id}")
    click.echo(f"Deleted custom food {food_id}.")


@click.group()
def diary() -> None:
    """Log and inspect food diary entries."""


@diary.command("show")
@click.option(
    "--date", "entry_date", type=ISO_DATE, default=_today, show_default="today"
)
@click.pass_obj
def show_diary(context: CLIContext, entry_date: date) -> None:
    """Show diary entries for a date."""
    day = _date_string(entry_date)
    data = context.client.request("GET", f"/diary/{day}")
    if context.json_output:
        _echo_json(data)
        return
    if not data:
        click.echo(f"No diary entries for {day}.")
        return
    click.echo(day)
    for entry in data:
        click.echo(
            f"[{entry['id']}] {entry['meal_type']}: {entry['food_name']} - "
            f"{_number(entry['amount'])} {entry['unit']} | "
            f"{_macro_summary(entry['nutrients_total'])}"
        )


@diary.command("search")
@click.argument("query")
@click.pass_obj
def search_diary(context: CLIContext, query: str) -> None:
    """Search diary history by food name."""
    data = context.client.request("GET", "/diary/search", params={"q": query})
    if context.json_output:
        _echo_json(data)
        return
    if not data:
        click.echo(f"No diary entries found for {query!r}.")
        return
    for entry in data:
        click.echo(
            f"[{entry['id']}] {entry['date']} {entry['meal_type']}: "
            f"{entry['food_name']} - {_number(entry['amount'])} {entry['unit']} | "
            f"{_macro_summary(entry['nutrients_total'])}"
        )


@diary.command("add")
@click.argument("food_id", type=int)
@click.argument("amount", type=click.FloatRange(min=0, min_open=True))
@click.argument("unit")
@click.option(
    "--meal",
    "meal_type",
    type=click.Choice(MEALS),
    default="snack",
    show_default=True,
)
@click.option(
    "--date", "entry_date", type=ISO_DATE, default=_today, show_default="today"
)
@click.pass_obj
def add_diary_entry(
    context: CLIContext,
    food_id: int,
    amount: float,
    unit: str,
    meal_type: str,
    entry_date: date,
) -> None:
    """Log FOOD_ID with an AMOUNT and UNIT."""
    day = _date_string(entry_date)
    data = context.client.request(
        "POST",
        f"/diary/{day}/entries",
        json={
            "food_id": food_id,
            "amount": amount,
            "unit": unit,
            "meal_type": meal_type,
        },
    )
    if context.json_output:
        _echo_json(data)
        return
    click.echo(
        f"Logged {data['food_name']} to {meal_type} on {day}: "
        f"{_number(data['amount'])} {data['unit']} "
        f"({_macro_summary(data['nutrients_total'])})"
    )


@diary.command("update")
@click.argument("entry_id", type=int)
@click.option("--amount", type=click.FloatRange(min=0, min_open=True))
@click.option("--unit")
@click.option("--meal", "meal_type", type=click.Choice(MEALS))
@click.pass_obj
def update_diary_entry(
    context: CLIContext,
    entry_id: int,
    amount: float | None,
    unit: str | None,
    meal_type: str | None,
) -> None:
    """Update a diary entry."""
    body = {
        key: value
        for key, value in {
            "amount": amount,
            "unit": unit,
            "meal_type": meal_type,
        }.items()
        if value is not None
    }
    if not body:
        raise click.UsageError("Provide --amount, --unit, or --meal")
    result = context.client.request(
        "PATCH",
        f"/diary/entries/{entry_id}",
        json=body,
    )
    _echo_json(result)


@diary.command("delete")
@click.argument("entry_id", type=int)
@click.option("--yes", is_flag=True, help="Delete without confirmation.")
@click.pass_obj
def delete_diary_entry(context: CLIContext, entry_id: int, yes: bool) -> None:
    """Delete a diary entry."""
    if not yes:
        click.confirm(f"Delete diary entry {entry_id}?", abort=True)
    context.client.request("DELETE", f"/diary/entries/{entry_id}")
    if context.json_output:
        _echo_json({"deleted": entry_id})
        return
    click.echo(f"Deleted diary entry {entry_id}.")


@click.group()
def stats() -> None:
    """View nutrition totals."""


@stats.command("daily")
@click.argument("day", type=ISO_DATE, required=False, default=_today)
@click.pass_obj
def daily_stats(context: CLIContext, day: date) -> None:
    """Show nutrition totals for DAY (defaults to today)."""
    day_string = _date_string(day)
    data = context.client.request("GET", f"/stats/daily/{day_string}")
    if context.json_output:
        _echo_json(data)
        return
    click.echo(
        f"{day_string}: {data['entry_count']} entries | {_macro_summary(data['total'])}"
    )
    activity = data.get("activity")
    if activity:
        click.echo(f"Activity: {activity['steps']:,} steps ({activity['source']})")


@stats.command("range")
@click.argument("start", type=ISO_DATE)
@click.argument("end", type=ISO_DATE)
@click.pass_obj
def range_stats(context: CLIContext, start: date, end: date) -> None:
    """Show daily totals from START through END."""
    if start > end:
        raise click.UsageError("START must not be after END")
    data = context.client.request(
        "GET",
        "/stats/range",
        params={"start": _date_string(start), "end": _date_string(end)},
    )
    if context.json_output:
        _echo_json(data)
        return
    if not data:
        click.echo("No diary entries in this date range.")
        return
    for day in data:
        click.echo(
            f"{day['date']}: {day['entry_count']} entries | "
            f"{_macro_summary(day['total'])}"
        )


@click.group()
def weight() -> None:
    """Log and inspect body weight."""


@weight.command("add")
@click.argument("value", type=click.FloatRange(min=0, min_open=True))
@click.option(
    "--unit",
    type=click.Choice(["kg", "lb"], case_sensitive=False),
    default="kg",
    show_default=True,
)
@click.option(
    "--date", "entry_date", type=ISO_DATE, default=_today, show_default="today"
)
@click.option("--notes")
@click.pass_obj
def add_weight(
    context: CLIContext,
    value: float,
    unit: str,
    entry_date: date,
    notes: str | None,
) -> None:
    """Log a body weight measurement."""
    weight_kg = value if unit.lower() == "kg" else value / POUNDS_PER_KILOGRAM
    body: dict[str, Any] = {
        "date": _date_string(entry_date),
        "weight_kg": weight_kg,
    }
    if notes is not None:
        body["notes"] = notes
    data = context.client.request("POST", "/weight", json=body)
    if context.json_output:
        _echo_json(data)
        return
    click.echo(
        f"Logged {_number(data['weight_kg'])} kg for {data['date']} "
        f"(entry {data['id']})."
    )


@weight.command("update")
@click.argument("entry_id", type=int)
@click.option("--kg", type=click.FloatRange(min=0, min_open=True))
@click.option("--lb", type=click.FloatRange(min=0, min_open=True))
@click.option("--notes")
@click.pass_obj
def update_weight(
    context: CLIContext,
    entry_id: int,
    kg: float | None,
    lb: float | None,
    notes: str | None,
) -> None:
    """Update a weight entry."""
    if kg is not None and lb is not None:
        raise click.UsageError("--kg and --lb cannot be combined")
    body: dict[str, Any] = {}
    if kg is not None:
        body["weight_kg"] = kg
    elif lb is not None:
        body["weight_kg"] = lb / POUNDS_PER_KILOGRAM
    if notes is not None:
        body["notes"] = notes
    if not body:
        raise click.UsageError("Provide --kg, --lb, or --notes")
    result = context.client.request(
        "PATCH",
        f"/weight/{entry_id}",
        json=body,
    )
    _echo_json(result)


@weight.command("list")
@click.option("--date", "entry_date", type=ISO_DATE)
@click.option("--start", type=ISO_DATE)
@click.option("--end", type=ISO_DATE)
@click.pass_obj
def list_weight(
    context: CLIContext,
    entry_date: date | None,
    start: date | None,
    end: date | None,
) -> None:
    """List weight entries; defaults to today."""
    if entry_date and (start or end):
        raise click.UsageError("--date cannot be combined with --start or --end")
    if bool(start) != bool(end):
        raise click.UsageError("--start and --end must be used together")
    if start and end and start > end:
        raise click.UsageError("--start must not be after --end")

    if start and end:
        params = {"start": _date_string(start), "end": _date_string(end)}
    else:
        today = datetime.now().astimezone().date()
        params = {"date": _date_string(entry_date or today)}
    data = context.client.request("GET", "/weight", params=params)
    if context.json_output:
        _echo_json(data)
        return
    if not data:
        click.echo("No weight entries found.")
        return
    for entry in data:
        notes = f" - {entry['notes']}" if entry.get("notes") else ""
        click.echo(
            f"[{entry['id']}] {entry['date']}: {_number(entry['weight_kg'])} kg{notes}"
        )


@weight.command("delete")
@click.argument("entry_id", type=int)
@click.option("--yes", is_flag=True, help="Delete without confirmation.")
@click.pass_obj
def delete_weight(context: CLIContext, entry_id: int, yes: bool) -> None:
    """Delete a weight entry."""
    if not yes:
        click.confirm(f"Delete weight entry {entry_id}?", abort=True)
    context.client.request("DELETE", f"/weight/{entry_id}")
    click.echo(f"Deleted weight entry {entry_id}.")
