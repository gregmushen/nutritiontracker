"""
Import McCance and Widdowson's Composition of Foods Integrated Dataset (CoFID).

Usage:
    python -m scripts.import_cofid <path_to_cofid_xlsx> [db_path]

Download the workbook ("McCance_Widdowsons_Composition_of_Foods_Integrated_
Dataset_2021.xlsx") from:
    https://www.gov.uk/government/publications/composition-of-foods-integrated-dataset-cofid

Published under the Open Government Licence v3.0. Requires the `data-import`
extra for openpyxl:  pip install -e ".[data-import]"
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import get_connection, init_schema
from app.providers.cofid import read_cofid_workbook
from app.repositories.foods import FoodRepository


def import_cofid(file_path: str, db_path: str | None = None) -> int:
    conn = get_connection(Path(db_path) if db_path else None)
    init_schema(conn)
    repo = FoodRepository(conn)
    repo.ensure_fts()

    count = 0
    batch_size = 500
    for food in read_cofid_workbook(file_path):
        repo.create_no_commit(**food)
        count += 1
        if count % batch_size == 0:
            conn.commit()
            print(f"  Imported {count} foods...")
    conn.commit()

    print(f"Done. Imported {count} CoFID foods.")
    conn.close()
    return count


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("xlsx_path")
    parser.add_argument("db_path", nargs="?")
    args = parser.parse_args()
    import_cofid(args.xlsx_path, args.db_path)
