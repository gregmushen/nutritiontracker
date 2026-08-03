"""
Import a personal Cronometer export.

Usage:
    python -m scripts.import_cronometer <path_to_export_dir> [db_path]
        [--user-id=ID]

The export directory is the one holding `cronometer.sqlite3` alongside a
`raw/mobile/food_details/` store, as produced by the Cronometer crawler.

Only foods are imported, each at its per-100 g composition, tagged with the
Cronometer food id and its upstream database.

NOTE: a Cronometer export mixes openly licensed data with proprietary databases
(NCCDB, CRDB, Nutritionix). Importing your own export for your own use is
personal use, not redistribution — do not republish the resulting rows or serve
them publicly.
"""

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings
from app.database import get_connection, init_schema
from app.providers.cronometer import read_cronometer_export, unresolved_food_names
from app.repositories.foods import FoodRepository


def import_cronometer(
    export_dir: str,
    db_path: str | None = None,
    owner_user_id: int | None = None,
) -> int:
    conn = get_connection(Path(db_path) if db_path else None)
    init_schema(conn)
    repo = FoodRepository(conn)
    repo.ensure_fts()
    if owner_user_id is None:
        owner_user_id = settings.default_user_id
    if conn.execute(
        "SELECT 1 FROM users WHERE id = ?", (owner_user_id,)
    ).fetchone() is None:
        conn.close()
        raise ValueError(f"No user {owner_user_id}; create the user before importing")

    by_source: Counter[str] = Counter()
    count = 0
    batch_size = 500
    for food in read_cronometer_export(export_dir):
        repo.create_no_commit(**food, owner_user_id=owner_user_id)
        by_source[food["source"]] += 1
        count += 1
        if count % batch_size == 0:
            conn.commit()
            print(f"  Imported {count} foods...")
    conn.commit()

    skipped = unresolved_food_names(export_dir)
    if skipped:
        print(
            f"\nSkipped {len(skipped)} logged foods with no per-100 g record "
            "(their values are per an unrecorded serving and cannot be scaled):"
        )
        for name in skipped:
            print(f"  - {name}")

    print(f"\nDone. Imported {count} Cronometer foods.")
    for source, total in by_source.most_common():
        print(f"  {source:20s} {total}")
    conn.close()
    return count


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("export_dir")
    parser.add_argument("db_path", nargs="?")
    parser.add_argument("--user-id", type=int, default=settings.default_user_id)
    args = parser.parse_args()
    import_cronometer(args.export_dir, args.db_path, args.user_id)
