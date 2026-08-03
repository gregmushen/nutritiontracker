"""
Import the Canadian Nutrient File (CNF).

Usage:
    python -m scripts.import_cnf <path_to_unpacked_cnf_dir> [db_path]

Download and unpack the CSV bundle from:
    https://open.canada.ca/data/en/dataset/1b6139bd-ed7e-4043-bc28-ff00e10f3109

Published by Health Canada under the Open Government Licence - Canada.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import get_connection, init_schema
from app.providers.cnf import read_cnf_directory
from app.repositories.foods import FoodRepository


def import_cnf(directory: str, db_path: str | None = None) -> int:
    conn = get_connection(Path(db_path) if db_path else None)
    init_schema(conn)
    repo = FoodRepository(conn)
    repo.ensure_fts()

    count = 0
    batch_size = 500
    for food in read_cnf_directory(directory):
        repo.create_no_commit(**food)
        count += 1
        if count % batch_size == 0:
            conn.commit()
            print(f"  Imported {count} foods...")
    conn.commit()

    print(f"Done. Imported {count} CNF foods.")
    conn.close()
    return count


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cnf_dir")
    parser.add_argument("db_path", nargs="?")
    args = parser.parse_args()
    import_cnf(args.cnf_dir, args.db_path)
