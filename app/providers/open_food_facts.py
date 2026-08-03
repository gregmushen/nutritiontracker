import httpx

from app.models.food import NUTRIENT_FIELDS

OFF_API_URL = "https://world.openfoodfacts.org/api/v2/product/{barcode}.json"
OFF_TIMEOUT = 5.0  # seconds

# field -> (OFF nutrient keys, unit OFF stores the per-100g value in, our unit).
#
# The middle element is the unit of the `<nutrient>_100g` figure, which OFF
# always normalizes: grams for every nutrient, kcal for energy. It is *not* the
# `<nutrient>_unit` the contributor typed in — that one describes the raw
# `value`/`serving` fields and is only used as an override when present.
OFF_NUTRIENT_MAP = {
    "calories_kcal": (("energy-kcal",), "kcal", "kcal"),
    "protein_g": (("proteins",), "g", "g"),
    "carbs_g": (("carbohydrates",), "g", "g"),
    "fat_g": (("fat",), "g", "g"),
    "sugar_g": (("sugars",), "g", "g"),
    "added_sugar_g": (("added-sugars",), "g", "g"),
    "saturated_fat_g": (("saturated-fat",), "g", "g"),
    "trans_fat_g": (("trans-fat",), "g", "g"),
    "monounsaturated_fat_g": (("monounsaturated-fat",), "g", "g"),
    "polyunsaturated_fat_g": (("polyunsaturated-fat",), "g", "g"),
    "fiber_g": (("fiber",), "g", "g"),
    "cholesterol_mg": (("cholesterol",), "g", "mg"),
    "caffeine_mg": (("caffeine",), "g", "mg"),
    "sodium_mg": (("sodium",), "g", "mg"),
    "potassium_mg": (("potassium",), "g", "mg"),
    "calcium_mg": (("calcium",), "g", "mg"),
    "iron_mg": (("iron",), "g", "mg"),
    "magnesium_mg": (("magnesium",), "g", "mg"),
    "zinc_mg": (("zinc",), "g", "mg"),
    "phosphorus_mg": (("phosphorus",), "g", "mg"),
    "copper_mg": (("copper",), "g", "mg"),
    "manganese_mg": (("manganese",), "g", "mg"),
    "selenium_ug": (("selenium",), "g", "ug"),
    "chromium_ug": (("chromium",), "g", "ug"),
    "iodine_ug": (("iodine",), "g", "ug"),
    "vitamin_a_ug": (("vitamin-a",), "g", "ug"),
    "vitamin_c_mg": (("vitamin-c",), "g", "mg"),
    "vitamin_d_ug": (("vitamin-d",), "g", "ug"),
    "vitamin_e_mg": (("vitamin-e",), "g", "mg"),
    "vitamin_k_ug": (("vitamin-k",), "g", "ug"),
    "thiamin_mg": (("vitamin-b1",), "g", "mg"),
    "riboflavin_mg": (("vitamin-b2",), "g", "mg"),
    "vitamin_b6_mg": (("vitamin-b6",), "g", "mg"),
    "vitamin_b12_ug": (("vitamin-b12",), "g", "ug"),
    "niacin_mg": (("vitamin-pp", "niacin"), "g", "mg"),
    "pantothenic_acid_mg": (("pantothenic-acid",), "g", "mg"),
    "biotin_ug": (("biotin",), "g", "ug"),
    "folate_ug": (("folates",), "g", "ug"),
    "folic_acid_ug": (("vitamin-b9",), "g", "ug"),
    "choline_mg": (("choline",), "g", "mg"),
}

_UNIT_FACTORS_TO_GRAMS = {
    "g": 1,
    "mg": 0.001,
    "ug": 0.000001,
    "mcg": 0.000001,
}


def _normalized_unit(unit: str | None, default: str) -> str:
    """Canonicalize an OFF unit string, falling back when it is missing.

    OFF leaves `unit` null or blank on a small number of records, so `default`
    (the unit OFF stores the per-100g value in) stands in for those.
    """
    if not unit:
        return default
    return unit.lower().replace("μ", "u").replace("µ", "u")


def _convert_unit(value: float, source_unit: str, target_unit: str) -> float:
    if source_unit == target_unit:
        return value
    if source_unit == "kcal" or target_unit == "kcal":
        raise ValueError(f"Cannot convert {source_unit} to {target_unit}")
    return value * _UNIT_FACTORS_TO_GRAMS[source_unit] / _UNIT_FACTORS_TO_GRAMS[target_unit]


def _parse_serving_quantity(raw: dict) -> float | None:
    val = raw.get("serving_quantity")
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _parse_product_quantity(raw: dict) -> float | None:
    value = raw.get("product_quantity")
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _get_nutrient_value(
    nutriments: dict, source_keys: tuple[str, ...], default_unit: str, target_unit: str
) -> float | None:
    """Return the converted per-100g value, or None when OFF does not report it.

    None means "not known" so it stays distinguishable from a label that
    genuinely declares zero.
    """
    for source_key in source_keys:
        value = nutriments.get(f"{source_key}_100g")
        if value is None:
            continue
        try:
            source_unit = _normalized_unit(nutriments.get(f"{source_key}_unit"), default_unit)
            return _convert_unit(float(value), source_unit, target_unit)
        except (AttributeError, KeyError, TypeError, ValueError):
            return None
    return None


def normalize_off_food(raw: dict) -> dict:
    nutriments = raw.get("nutriments", {})
    nutrients = {
        field: _get_nutrient_value(nutriments, source_keys, source_unit, target_unit)
        for field, (source_keys, source_unit, target_unit) in OFF_NUTRIENT_MAP.items()
    }

    return {
        "source": "open_food_facts",
        "source_code": raw.get("code", ""),
        "name": raw.get("product_name", ""),
        "brand": raw.get("brands") or None,
        "barcode": raw.get("code") or None,
        "image_url": raw.get("image_url") or None,
        "serving_quantity": _parse_serving_quantity(raw),
        "serving_unit": "g",
        "serving_size_text": raw.get("serving_size") or None,
        "ingredients_text": raw.get("ingredients_text") or None,
        "allergens_tags": raw.get("allergens_tags") or [],
        "dietary_tags": raw.get("ingredients_analysis_tags") or [],
        "categories_tags": raw.get("categories_tags") or [],
        "labels_tags": raw.get("labels_tags") or [],
        "countries_tags": raw.get("countries_tags") or [],
        "nutriscore_grade": raw.get("nutriscore_grade") or None,
        "nova_group": raw.get("nova_group"),
        "product_quantity": _parse_product_quantity(raw),
        "product_quantity_unit": raw.get("product_quantity_unit") or None,
        **nutrients,
    }


def fetch_off_by_barcode(barcode: str) -> dict | None:
    """Fetch a single product from the live OFF API by barcode.

    Returns a normalized food dict if the product exists and has nutrient data,
    otherwise returns None.
    """
    try:
        resp = httpx.get(
            OFF_API_URL.format(barcode=barcode),
            timeout=OFF_TIMEOUT,
            headers={"User-Agent": "NutritionTracker/1.0"},
        )
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, ValueError):
        return None

    if data.get("status") != 1:
        return None

    product = data.get("product", {})
    name = product.get("product_name", "").strip()
    if not name:
        return None

    normalized = normalize_off_food(product)
    # Zero is a reported measurement, not the absence of nutrient data.
    if not any(normalized.get(field) is not None for field in NUTRIENT_FIELDS):
        return None

    return normalized
