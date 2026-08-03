"""Bulk import Open Food Facts Parquet data into the nutrition tracker database.

Usage:
    python -m scripts.import_off_parquet <path_to_food_parquet> [db_path]
        [--country=en:united-states]
"""

import argparse
from pathlib import Path

from app.database import get_connection, init_schema
from app.providers.open_food_facts import normalize_off_food
from app.repositories.foods import FoodRepository

PARQUET_COLUMNS = (
    "code",
    "product_name",
    "brands",
    "allergens_tags",
    "ingredients_analysis_tags",
    "categories_tags",
    "labels_tags",
    "countries_tags",
    "ingredients_text",
    "nutriscore_grade",
    "nova_group",
    "product_quantity",
    "product_quantity_unit",
    "serving_quantity",
    "serving_size",
    "nutriments",
)

REQUIRED_PARQUET_COLUMNS = frozenset({"code", "product_name", "nutriments"})

NORMALIZED_FIELDS_BY_COLUMN = {
    "brands": ("brand",),
    "allergens_tags": ("allergens_tags",),
    "ingredients_analysis_tags": ("dietary_tags",),
    "categories_tags": ("categories_tags",),
    "labels_tags": ("labels_tags",),
    "countries_tags": ("countries_tags",),
    "ingredients_text": ("ingredients_text",),
    "nutriscore_grade": ("nutriscore_grade",),
    "nova_group": ("nova_group",),
    "product_quantity": ("product_quantity",),
    "product_quantity_unit": ("product_quantity_unit",),
    "serving_quantity": ("serving_quantity", "serving_unit"),
    "serving_size": ("serving_size_text",),
}


def _product_name(names: list[dict] | None) -> str:
    if not names:
        return ""
    preferred = ("main", "en")
    for language in preferred:
        for name in names:
            if name.get("lang") == language and name.get("text"):
                return name["text"].strip()
    return next((name["text"].strip() for name in names if name.get("text")), "")


def parquet_row_to_off_product(row: dict) -> dict:
    nutriments = {}
    for nutrient in row.get("nutriments") or []:
        name = nutrient.get("name")
        if not name:
            continue
        # Only `100g` is carried over. The dump's `unit` column describes the
        # contributor-entered `value`/`serving` fields, not `100g`, which OFF
        # always normalizes to grams (kcal for energy). Forwarding it as
        # `<name>_unit` would make the normalizer rescale an already-normalized
        # figure — e.g. salt `value=1785 unit=mg` alongside `100g=12.7` grams.
        nutriments[f"{name}_100g"] = nutrient.get("100g")

    return {
        "code": row.get("code") or "",
        "product_name": _product_name(row.get("product_name")),
        "brands": row.get("brands"),
        "allergens_tags": row.get("allergens_tags") or [],
        "ingredients_analysis_tags": row.get("ingredients_analysis_tags") or [],
        "categories_tags": row.get("categories_tags") or [],
        "labels_tags": row.get("labels_tags") or [],
        "countries_tags": row.get("countries_tags") or [],
        "ingredients_text": _product_name(row.get("ingredients_text")),
        "nutriscore_grade": row.get("nutriscore_grade"),
        "nova_group": row.get("nova_group"),
        "product_quantity": row.get("product_quantity"),
        "product_quantity_unit": row.get("product_quantity_unit"),
        "serving_quantity": row.get("serving_quantity"),
        "serving_size": row.get("serving_size"),
        "nutriments": nutriments,
    }


def import_off_parquet(
    file_path: str, db_path: str | None = None, country: str | None = None
) -> None:
    try:
        import pyarrow.parquet as pq
    except ImportError as error:
        raise RuntimeError(
            "Parquet imports require the data-import extra: pip install -e '.[data-import]'"
        ) from error

    conn = get_connection(Path(db_path) if db_path else None)
    init_schema(conn)
    repo = FoodRepository(conn)
    repo.ensure_fts()

    imported = 0
    skipped = 0
    parquet_file = pq.ParquetFile(file_path)
    available_columns = frozenset(parquet_file.schema_arrow.names)
    required_columns = set(REQUIRED_PARQUET_COLUMNS)
    if country:
        required_columns.add("countries_tags")
    missing_columns = sorted(required_columns - available_columns)
    if missing_columns:
        raise ValueError(
            "Open Food Facts Parquet file is missing required columns: "
            + ", ".join(missing_columns)
        )
    columns = [
        column for column in PARQUET_COLUMNS if column in available_columns
    ]
    for batch in parquet_file.iter_batches(batch_size=10_000, columns=columns):
        for row in batch.to_pylist():
            if country and country not in (row.get("countries_tags") or []):
                skipped += 1
                continue
            raw = parquet_row_to_off_product(row)
            if not raw["code"] or not raw["product_name"]:
                skipped += 1
                continue
            normalized = normalize_off_food(raw)
            for column, fields in NORMALIZED_FIELDS_BY_COLUMN.items():
                if column not in available_columns:
                    for field in fields:
                        normalized.pop(field, None)
            repo.create_no_commit(**normalized)
            imported += 1
            if imported % 5_000 == 0:
                conn.commit()
                print(f"  Imported {imported} foods (skipped {skipped})...")
    conn.commit()
    conn.close()
    print(f"Done. Imported {imported} Open Food Facts foods (skipped {skipped}).")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("parquet_path")
    parser.add_argument("db_path", nargs="?")
    parser.add_argument("--country")
    args = parser.parse_args()
    import_off_parquet(args.parquet_path, args.db_path, args.country)


if __name__ == "__main__":
    main()
