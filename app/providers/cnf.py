"""Normalizer for the Canadian Nutrient File (CNF).

CNF is published by Health Canada under the Open Government Licence - Canada as
a set of relational CSV files rather than one table per food:

    Food_Name.csv                 one row per food
    Nutrient_Name.csv             nutrient code -> symbol, unit
    Nutrient_Amount.csv           one row per (food, nutrient) measurement
    Measure_Weight_Conversion.csv one row per (food, household measure)
    Measure_Name.csv              measure code -> "1 cup (250 ml)"

Because measurements are rows rather than columns, a nutrient a food was never
assayed for simply has no row, which maps cleanly onto None: CNF states what it
measured and stays silent otherwise, so nothing has to be inferred from a zero.

Nutrient codes are the original USDA SR nutrient numbers (203 protein, 601
cholesterol), and amounts are per 100 g of edible portion.
"""

import csv
from collections.abc import Iterator
from pathlib import Path

CNF_SOURCE = "cnf"

FOOD_FILE = "Food_Name.csv"
NUTRIENT_NAME_FILE = "Nutrient_Name.csv"
NUTRIENT_AMOUNT_FILE = "Nutrient_Amount.csv"
MEASURE_CONVERSION_FILE = "Measure_Weight_Conversion.csv"
MEASURE_NAME_FILE = "Measure_Name.csv"

# Measure_Type 3 is "Refuse" (the inedible part of a food, e.g. 28 g of stems
# on spinach) and 9 is "Yield" (weight change on cooking). Only type 6,
# "User-defined", is an actual household portion, so it alone can be a serving.
HOUSEHOLD_MEASURE_TYPE = "6"

# Our field -> CNF nutrient codes, best first.
FIELD_NUTRIENTS: dict[str, tuple[str, ...]] = {
    "calories_kcal": ("208",),
    "protein_g": ("203",),
    "fat_g": ("204",),
    "carbs_g": ("205",),
    "sugar_g": ("269",),
    "fiber_g": ("291",),
    "saturated_fat_g": ("606",),
    "monounsaturated_fat_g": ("645",),
    "polyunsaturated_fat_g": ("646",),
    "trans_fat_g": ("605",),
    "cholesterol_mg": ("601",),
    "sodium_mg": ("307",),
    "potassium_mg": ("306",),
    "calcium_mg": ("301",),
    "magnesium_mg": ("304",),
    "phosphorus_mg": ("305",),
    "iron_mg": ("303",),
    "copper_mg": ("312",),
    "zinc_mg": ("309",),
    "manganese_mg": ("315",),
    "selenium_ug": ("317",),
    "vitamin_a_ug": ("320",),
    "vitamin_d_ug": ("328",),
    "vitamin_e_mg": ("323",),
    "vitamin_k_ug": ("430",),
    "thiamin_mg": ("404",),
    "riboflavin_mg": ("405",),
    "niacin_mg": ("406",),
    "vitamin_b6_mg": ("415",),
    "vitamin_b12_ug": ("418",),
    # Dietary folate equivalents match how USDA reports folate; fall back to
    # total folacin for foods measured before DFE was adopted.
    "folate_ug": ("435", "417"),
    "folic_acid_ug": ("431",),
    "pantothenic_acid_mg": ("410",),
    "biotin_ug": ("416",),
    "vitamin_c_mg": ("401",),
    "choline_mg": ("421",),
    "caffeine_mg": ("262",),
}

# CNF does not report these at all; they stay unknown rather than zero.
UNREPORTED_FIELDS = (
    "added_sugar_g",
    "chromium_ug",
    "iodine_ug",
)

# CNF publishes each nutrient in a fixed unit that already matches our field
# suffix. Imports verify this rather than trusting it, so a future release that
# switches a nutrient's unit fails loudly instead of silently scaling values.
EXPECTED_UNITS = {
    "g": "gram",
    "mg": "milligram",
    "ug": "microgram",
    "kcal": "kilocalorie",
}


def parse_cnf_value(raw) -> float | None:
    """Convert one CNF nutrient amount into a value, or None when absent."""
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _field_unit(field: str) -> str:
    return field.rsplit("_", 1)[-1]


def require_published_unit(code: str, units_by_code: dict[str, str]) -> None:
    """Fail if a nutrient we import has no unit published in the metadata.

    `check_nutrient_units` can only compare units it was handed, so a code
    missing from ``Nutrient_Name.csv`` would import completely unverified —
    the exact silent 1000x rescale that checking units exists to prevent.
    """
    if code not in units_by_code:
        raise ValueError(
            f"CNF nutrient {code} has no unit in {NUTRIENT_NAME_FILE}; "
            "refusing to import a value whose unit cannot be verified"
        )


def check_nutrient_units(units_by_code: dict[str, str]) -> None:
    """Fail if CNF reports a mapped nutrient in a unit we do not expect."""
    for field, codes in FIELD_NUTRIENTS.items():
        expected = EXPECTED_UNITS[_field_unit(field)]
        for code in codes:
            actual = units_by_code.get(code)
            if actual is None:
                continue
            if actual.strip().lower() != expected:
                raise ValueError(
                    f"CNF nutrient {code} for {field} is reported in "
                    f"{actual!r}, expected {expected!r}"
                )


def normalize_cnf_food(
    amounts: dict[str, float | None],
    *,
    food_code: str,
    name: str,
    group: str | None = None,
    serving_grams: float | None = None,
    serving_text: str | None = None,
) -> dict:
    """Build a food record from one food's CNF nutrient amounts."""
    nutrients: dict[str, float | None] = {}
    for field, codes in FIELD_NUTRIENTS.items():
        value = None
        for code in codes:
            value = amounts.get(code)
            if value is not None:
                break
        nutrients[field] = value
    for field in UNREPORTED_FIELDS:
        nutrients[field] = None

    return {
        "source": CNF_SOURCE,
        "source_code": food_code,
        "name": name,
        "brand": None,
        "barcode": None,
        "base_quantity": 100,
        "base_unit": "g",
        "serving_quantity": serving_grams,
        "serving_unit": "g" if serving_grams else None,
        "serving_size_text": serving_text,
        "categories_tags": [f"cnf:{group}"] if group else [],
        **nutrients,
    }


def _read_csv(directory: Path, filename: str) -> Iterator[dict]:
    path = directory / filename
    if not path.exists():
        raise ValueError(f"CNF directory is missing {filename} (looked in {directory})")
    # CNF ships UTF-8 with a BOM on the header row.
    with path.open(encoding="utf-8-sig", newline="") as handle:
        yield from csv.DictReader(handle)


def _wanted_codes() -> set[str]:
    return {code for codes in FIELD_NUTRIENTS.values() for code in codes}


def _read_servings(directory: Path) -> dict[str, tuple[float, str | None]]:
    """First usable household measure per food, as (grams, description)."""
    measure_names = {
        row["Measure_Code"]: (row.get("Measure_Description_and_Unit_EN") or "").strip()
        for row in _read_csv(directory, MEASURE_NAME_FILE)
    }
    servings: dict[str, tuple[float, str | None]] = {}
    for row in _read_csv(directory, MEASURE_CONVERSION_FILE):
        food_code = row["Food_Code"]
        if food_code in servings:
            continue
        if (row.get("Measure_Type_Code") or "").strip() != HOUSEHOLD_MEASURE_TYPE:
            continue
        grams = parse_cnf_value(row.get("Measure_Weight_Conversion"))
        if not grams:
            continue
        servings[food_code] = (grams, measure_names.get(row["Measure_Code"]) or None)
    return servings


def read_cnf_directory(directory: str | Path) -> Iterator[dict]:
    """Yield normalized foods from an unpacked CNF CSV bundle."""
    directory = Path(directory)

    units_by_code = {
        row["Nutrient_Code"]: row["Nutrient_Unit"]
        for row in _read_csv(directory, NUTRIENT_NAME_FILE)
    }
    check_nutrient_units(units_by_code)

    wanted = _wanted_codes()
    amounts: dict[str, dict[str, float | None]] = {}
    for row in _read_csv(directory, NUTRIENT_AMOUNT_FILE):
        code = row["Nutrient_Code"]
        if code not in wanted:
            continue
        require_published_unit(code, units_by_code)
        value = parse_cnf_value(row.get("Nutrient_Amount"))
        if value is None:
            continue
        amounts.setdefault(row["Food_Code"], {})[code] = value

    servings = _read_servings(directory)

    for row in _read_csv(directory, FOOD_FILE):
        food_code = (row.get("Food_Code") or "").strip()
        name = (row.get("Food_Description_EN") or "").strip()
        if not food_code or not name:
            continue
        serving_grams, serving_text = servings.get(food_code, (None, None))
        yield normalize_cnf_food(
            amounts.get(food_code, {}),
            food_code=food_code,
            name=name,
            group=(row.get("CNF_Food_Group_Code") or "").strip() or None,
            serving_grams=serving_grams,
            serving_text=serving_text,
        )
