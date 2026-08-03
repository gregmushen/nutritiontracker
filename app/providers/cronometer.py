"""Normalizer for a personal Cronometer export.

Unlike the other providers in this package, this one does not read a published
national dataset. It reads a *personal data export* — the foods one account
actually logged — produced by crawling Cronometer's own APIs. It exists so that
foods a user has already curated elsewhere can be carried into this system with
their real provenance intact.

Licensing
---------
Cronometer serves foods drawn from several upstream databases, and two of the
largest are **not** openly licensed: NCCDB (University of Minnesota Nutrition
Coordinating Center) and CRDB (Cronometer's own restaurant and branded
database). Importing your own export for your own use is personal use, not
redistribution. The resulting rows must not be republished, redistributed, or
exposed through a public API, and no export data is committed to this
repository.

Layout of an export directory::

    cronometer.sqlite3                     crawl database (diary, referenced foods)
    raw/mobile/food_details/objects/**.json  one JSON document per food

``referenced_items`` records which foods the account actually used, but its
``enriched_json`` is inconsistent: some records are per 100 g while others are
per an unrecorded default serving (butter came out as 103 kcal — one
tablespoon), so scaling them is guesswork. The raw ``food_details`` documents
carry no such ambiguity: every one is per 100 g, keyed by numeric nutrient id,
and 150 nutrient ids were verified to agree exactly with the per-100 g
``enriched_json`` records. Those documents are therefore the only thing read
for nutrient values, and any food lacking one is skipped rather than guessed.

Nutrient ids are USDA SR nutrient numbers (203 protein, 601 cholesterol) with a
handful of Cronometer extensions in the 10000 range.
"""

import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path

CRONOMETER_SOURCE = "cronometer"

FOOD_DETAILS_DIR = Path("raw") / "mobile" / "food_details" / "objects"
CRAWL_DB = "cronometer.sqlite3"

# Our field -> Cronometer nutrient id.
FIELD_NUTRIENTS: dict[str, int] = {
    "calories_kcal": 208,
    "protein_g": 203,
    "carbs_g": 205,
    "fat_g": 204,
    "sugar_g": 269,
    "added_sugar_g": 10009,
    "saturated_fat_g": 606,
    "trans_fat_g": 605,
    "monounsaturated_fat_g": 645,
    "polyunsaturated_fat_g": 646,
    "fiber_g": 291,
    "cholesterol_mg": 601,
    "caffeine_mg": 262,
    "sodium_mg": 307,
    "potassium_mg": 306,
    "calcium_mg": 301,
    "iron_mg": 303,
    "magnesium_mg": 304,
    "zinc_mg": 309,
    "phosphorus_mg": 305,
    "copper_mg": 312,
    "manganese_mg": 315,
    "selenium_ug": 317,
    "chromium_ug": 10003,
    "iodine_ug": 10005,
    "vitamin_a_ug": 320,
    "vitamin_c_mg": 401,
    "vitamin_d_ug": 324,
    "vitamin_e_mg": 323,
    "vitamin_k_ug": 430,
    "thiamin_mg": 404,
    "riboflavin_mg": 405,
    "vitamin_b6_mg": 415,
    "vitamin_b12_ug": 418,
    "niacin_mg": 406,
    "pantothenic_acid_mg": 410,
    "biotin_ug": 10004,
    "folate_ug": 417,
    "choline_mg": 421,
}

# Cronometer reports no folic acid separately from total folate, so it stays
# unknown rather than being confused with the folate figure.
UNREPORTED_FIELDS = ("folic_acid_ug",)

# The unit each mapped nutrient is published in. Raw food documents carry bare
# numbers, so imports verify these against the units Cronometer labels the same
# ids with elsewhere in the export; a unit change then fails loudly instead of
# silently rescaling values.
PUBLISHED_UNITS: dict[int, str] = {
    208: "kcal",
    203: "g", 205: "g", 204: "g", 269: "g", 10009: "g",
    606: "g", 605: "g", 645: "g", 646: "g", 291: "g",
    601: "mg", 262: "mg", 307: "mg", 306: "mg", 301: "mg", 303: "mg",
    304: "mg", 309: "mg", 305: "mg", 312: "mg", 315: "mg",
    401: "mg", 323: "mg", 404: "mg", 405: "mg", 415: "mg", 406: "mg",
    410: "mg", 421: "mg",
    317: "ug", 10003: "ug", 10005: "ug", 320: "ug", 430: "ug",
    418: "ug", 10004: "ug", 417: "ug",
    # Cronometer publishes vitamin D in international units, not micrograms.
    324: "IU",
}

# Nutrients published in a unit our field does not use, and the factor that
# converts one published unit into ours. 1 ug of vitamin D is 40 IU.
UNIT_CONVERSIONS: dict[int, float] = {324: 1.0 / 40.0}

# Upstream databases that only reach this system through a Cronometer export.
# Each gets its own source code so the real provenance survives the import.
SOURCE_PREFIXES: dict[str, str] = {
    "NCCDB": "nccdb",
    "CRDB": "crdb",
    "Nutritionix": "nutritionix",
    "NUTTAB": "nuttab",
    "Custom": "cronometer_custom",
}

# Measures that just restate the base unit and so make a useless serving.
BARE_UNIT_MEASURES = frozenset(
    {"g", "gram", "grams", "mg", "kg", "ml", "l", "oz", "fl oz", "lb", "cc"}
)


def _field_unit(field: str) -> str:
    return field.rsplit("_", 1)[-1]


def check_nutrient_units(units_by_id: dict[int, str]) -> None:
    """Fail if the export labels a mapped nutrient with an unexpected unit."""
    for field, nutrient_id in FIELD_NUTRIENTS.items():
        actual = units_by_id.get(nutrient_id)
        if actual is None:
            continue
        # The export writes micrograms with the micro sign.
        normalized = actual.strip().replace("\u00b5", "u").replace("\u03bc", "u")
        expected = PUBLISHED_UNITS[nutrient_id]
        if normalized.lower() != expected.lower():
            raise ValueError(
                f"Cronometer nutrient {nutrient_id} for {field} is reported in "
                f"{actual!r}, expected {expected!r}"
            )


def parse_source(raw_source: str | None, food_id: int | str) -> tuple[str, str]:
    """Resolve Cronometer's ``source`` string to a (source code, id) pair.

    Foods drawn from a database this system imports directly (FoodData Central,
    USDA SR, CoFID, CNF) stay under the generic ``cronometer`` code keyed by
    Cronometer's own food id. Filing them under the native source code would
    collide with — and overwrite — the authoritative row from the full dataset,
    which is both more complete and better identified than one food pulled
    through a third party.
    """
    text = (raw_source or "").strip()
    prefix, _, remainder = text.partition(":")
    code = SOURCE_PREFIXES.get(prefix.strip())
    if code is None:
        return CRONOMETER_SOURCE, str(food_id)
    return code, remainder.strip() or str(food_id)


def _is_bare_measure(measure: dict) -> bool:
    return (measure.get("name") or "").strip().lower() in BARE_UNIT_MEASURES


def pick_serving(
    measures: list[dict], default_measure_id: int | None
) -> tuple[float | None, str | None]:
    """Choose a household serving as (grams, description).

    Cronometer's default measure is frequently plain grams, which says nothing
    a per-100 g record does not already say, so a named portion is preferred
    over it.
    """
    usable = [m for m in measures or [] if not m.get("hidden") and m.get("value")]
    if not usable:
        return None, None

    default = next((m for m in usable if m.get("id") == default_measure_id), None)
    named = next((m for m in usable if not _is_bare_measure(m)), None)

    chosen = default if default is not None and not _is_bare_measure(default) else named
    if chosen is None:
        return None, None

    grams = float(chosen["value"])
    amount = chosen.get("amount") or 1
    label = (chosen.get("name") or "").strip()
    text = f"{amount:g} {label}".strip() if label else None
    return grams, text


def normalize_cronometer_food(document: dict) -> dict:
    """Build a food record from one raw Cronometer ``food_details`` document."""
    food_id = document.get("id")
    amounts: dict[int, float] = {}
    for entry in document.get("nutrients") or []:
        nutrient_id = entry.get("id")
        amount = entry.get("amount")
        if nutrient_id is None or amount is None:
            continue
        amounts[int(nutrient_id)] = float(amount)

    nutrients: dict[str, float | None] = {}
    for field, nutrient_id in FIELD_NUTRIENTS.items():
        value = amounts.get(nutrient_id)
        if value is not None:
            factor = UNIT_CONVERSIONS.get(nutrient_id)
            if factor is not None:
                value *= factor
        nutrients[field] = value
    for field in UNREPORTED_FIELDS:
        nutrients[field] = None

    raw_source = document.get("source")
    source, source_code = parse_source(raw_source, food_id)
    serving_grams, serving_text = pick_serving(
        document.get("measures") or [], document.get("defaultMeasureId")
    )

    tags = [f"cronometer:{food_id}"]
    if raw_source:
        tags.append(f"cronometer-source:{raw_source}")

    return {
        "source": source,
        "source_code": source_code,
        "name": (document.get("name") or "").strip().rstrip(",").strip(),
        "brand": None,
        "barcode": next(iter(document.get("barcodes") or []), None),
        "base_quantity": 100,
        "base_unit": "g",
        "serving_quantity": serving_grams,
        "serving_unit": "g" if serving_grams else None,
        "serving_size_text": serving_text,
        "categories_tags": tags,
        **nutrients,
    }


def _food_details_dir(directory: Path) -> Path:
    path = directory / FOOD_DETAILS_DIR
    if not path.exists():
        raise ValueError(
            f"Cronometer export is missing {FOOD_DETAILS_DIR} (looked in {directory})"
        )
    return path


def read_food_documents(directory: str | Path) -> Iterator[dict]:
    """Yield each raw per-100 g food document in an export, newest id first."""
    seen: set[int] = set()
    for path in sorted(_food_details_dir(Path(directory)).rglob("*.json")):
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if not isinstance(document, dict):
            continue
        food_id = document.get("id")
        if food_id is None or "nutrients" not in document or food_id in seen:
            continue
        seen.add(food_id)
        yield document


def _units_from_crawl_db(directory: Path) -> dict[int, str]:
    """Nutrient units as labelled in the crawl database, for verification."""
    db_path = directory / CRAWL_DB
    if not db_path.exists():
        raise FileNotFoundError(f"Cronometer export is missing {CRAWL_DB}")
    units: dict[int, str] = {}
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "SELECT enriched_json FROM referenced_items WHERE enriched = 1"
        ).fetchall()
    finally:
        conn.close()
    for (payload,) in rows:
        try:
            record = json.loads(payload)
        except (TypeError, json.JSONDecodeError):
            continue
        for entry in record.get("nutrients") or []:
            nutrient_id, unit = entry.get("nutrient_id"), entry.get("unit")
            if nutrient_id is None or not unit:
                continue
            try:
                units.setdefault(int(nutrient_id), unit)
            except (TypeError, ValueError):
                continue
    return units


def unresolved_food_names(directory: str | Path) -> list[str]:
    """Names of logged foods with no per-100 g document, which are skipped."""
    directory = Path(directory)
    db_path = directory / CRAWL_DB
    if not db_path.exists():
        return []
    available = {document.get("id") for document in read_food_documents(directory)}
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "SELECT name, enriched_json FROM referenced_items WHERE enriched = 1"
        ).fetchall()
    except sqlite3.Error:
        return []
    finally:
        conn.close()

    missing = []
    for name, payload in rows:
        try:
            food_id = json.loads(payload).get("food_id")
        except (TypeError, json.JSONDecodeError):
            continue
        try:
            food_id = int(food_id)
        except (TypeError, ValueError):
            continue
        if food_id not in available:
            missing.append(name)
    return missing


def read_cronometer_export(directory: str | Path) -> Iterator[dict]:
    """Yield normalized foods from a personal Cronometer export directory."""
    directory = Path(directory)
    _food_details_dir(directory)
    units = _units_from_crawl_db(directory)
    check_nutrient_units(units)
    for document in read_food_documents(directory):
        required_ids = {
            int(entry["id"])
            for entry in document.get("nutrients") or []
            if entry.get("id") in PUBLISHED_UNITS and entry.get("amount") is not None
        }
        missing_ids = sorted(required_ids - units.keys())
        if missing_ids:
            missing = ", ".join(str(nutrient_id) for nutrient_id in missing_ids)
            raise ValueError(
                f"Cronometer export has no verified unit metadata for nutrient(s): "
                f"{missing}"
            )
        food = normalize_cronometer_food(document)
        if food["name"]:
            yield food
