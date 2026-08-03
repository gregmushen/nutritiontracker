"""
Import Frida, the Danish Food Composition Database.

Usage:
    python -m scripts.import_frida <path_to_frida_dataset_xlsx> [db_path]

Download "FCDB_<version>_Dataset.xlsx" from:
    https://doi.org/10.11583/DTU.32312844

Published by the National Food Institute, DTU, under CC BY 4.0. Requires the
`data-import` extra for openpyxl:  pip install -e ".[data-import]"
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import get_connection, init_schema
from app.providers.frida import read_frida_workbook
from app.repositories.foods import FoodRepository


def import_frida(file_path: str, db_path: str | None = None) -> int:
    conn = get_connection(Path(db_path) if db_path else None)
    init_schema(conn)
    repo = FoodRepository(conn)
    repo.ensure_fts()

    count = 0
    batch_size = 500
    for food in read_frida_workbook(file_path):
        repo.create_no_commit(**food)
        count += 1
        if count % batch_size == 0:
            conn.commit()
            print(f"  Imported {count} foods...")
    conn.commit()

    print(f"Done. Imported {count} Frida foods.")
    conn.close()
    return count


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("xlsx_path")
    parser.add_argument("db_path", nargs="?")
    args = parser.parse_args()
    import_frida(args.xlsx_path, args.db_path)
