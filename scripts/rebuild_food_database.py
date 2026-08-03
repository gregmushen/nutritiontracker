"""Build an optimized nutrition database from USDA and Open Food Facts exports.

Usage:
    python -m scripts.rebuild_food_database OUTPUT_DB OFF_PARQUET \
        --foundation-json=FILE --sr-legacy-json=FILE \
        [--foundation-csv-dir=DIR] [--country=en:united-states]
"""

import argparse
from pathlib import Path

from scripts.import_off_parquet import import_off_parquet
from scripts.import_usda import import_usda


def rebuild_database(
    output_path: Path,
    off_parquet_path: Path,
    *,
    foundation_json_path: Path,
    sr_legacy_json_path: Path,
    foundation_csv_dir: Path | None = None,
    country: str | None = "en:united-states",
) -> None:
    if output_path.exists():
        raise FileExistsError(f"Refusing to overwrite existing database: {output_path}")

    import_usda(str(sr_legacy_json_path), str(output_path))
    import_usda(
        str(foundation_json_path),
        str(output_path),
        str(foundation_csv_dir) if foundation_csv_dir else None,
    )
    import_off_parquet(str(off_parquet_path), str(output_path), country=country)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_db", type=Path)
    parser.add_argument("off_parquet", type=Path)
    parser.add_argument("--foundation-json", required=True, type=Path)
    parser.add_argument("--sr-legacy-json", required=True, type=Path)
    parser.add_argument("--foundation-csv-dir", type=Path)
    parser.add_argument("--country", default="en:united-states")
    args = parser.parse_args()

    rebuild_database(
        args.output_db,
        args.off_parquet,
        foundation_json_path=args.foundation_json,
        sr_legacy_json_path=args.sr_legacy_json,
        foundation_csv_dir=args.foundation_csv_dir,
        country=args.country,
    )


if __name__ == "__main__":
    main()
