"""Relink a diary entry to a different food, recomputing its stored nutrients.

Usage:
    python -m scripts.repoint_diary_entry <db> <entry_id> <food_id>

Label data records unmeasured micronutrients as zero, so an entry logged
against a barcode row understates everything the label omits. Pointing the same
entry at a reference row keeps the logged weight but recomputes totals from
analysed values.

The gram weight is preserved, so only entries logged in grams are repointed
without a unit conversion; anything else is rejected rather than guessed at.
"""

import argparse
import json
import sqlite3
from pathlib import Path

from app.repositories.foods import FoodRepository
from app.services.diary import build_food_snapshot, compute_entry_nutrients
from app.services.unit_conversion import convert_to_grams


def repoint(db_path: Path, entry_id: int, food_id: int) -> dict:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        entry = conn.execute(
            """SELECT id, user_id, unit, grams, food_id, food_name
               FROM diary_entries WHERE id = ?""",
            (entry_id,),
        ).fetchone()
        if entry is None:
            raise ValueError(f"No diary entry {entry_id}")
        if entry["unit"] != "g":
            raise ValueError(
                f"Entry {entry_id} is logged in {entry['unit']!r}; "
                "only gram entries can be repointed without a unit conversion"
            )

        raw_food = conn.execute("SELECT id FROM foods WHERE id = ?", (food_id,)).fetchone()
        if raw_food is None:
            raise ValueError(f"No food {food_id}")
        food_dict = FoodRepository(conn).get(food_id, user_id=entry["user_id"])
        if food_dict is None:
            raise ValueError(
                f"Food {food_id} is private to a different user than entry {entry_id}"
            )

        snapshot = build_food_snapshot(food_dict)
        conversion = convert_to_grams(
            entry["grams"],
            "g",
            density_g_per_ml=food_dict.get("density_g_per_ml"),
        )
        nutrients = compute_entry_nutrients(
            food_dict,
            conversion.amount_in(food_dict.get("base_unit", "g")),
        )

        conn.execute(
            """UPDATE diary_entries
               SET food_id = ?, food_snapshot = ?, food_name = ?, nutrients_total = ?,
                   updated_at = CURRENT_TIMESTAMP
               WHERE id = ?""",
            (food_id, json.dumps(snapshot), food_dict["name"], json.dumps(nutrients), entry_id),
        )
        conn.commit()
        return {
            "entry_id": entry_id,
            "grams": entry["grams"],
            "from": {"food_id": entry["food_id"], "name": entry["food_name"]},
            "to": {
                "food_id": food_id,
                "name": food_dict["name"],
                "source": food_dict["source"],
                "source_code": food_dict["source_code"],
            },
            "nutrients": nutrients,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("db", type=Path)
    parser.add_argument("entry_id", type=int)
    parser.add_argument("food_id", type=int)
    args = parser.parse_args()

    result = repoint(args.db, args.entry_id, args.food_id)
    print(f"Repointed entry {result['entry_id']} ({result['grams']}g)")
    print(f"  from: {result['from']['name']} (food {result['from']['food_id']})")
    to = result["to"]
    print(f"    to: {to['name']} [{to['source']}:{to['source_code']}] (food {to['food_id']})")
    for key in ("calories_kcal", "vitamin_e_mg", "vitamin_c_mg", "fiber_g", "fat_g"):
        print(f"       {key}: {result['nutrients'].get(key)}")


if __name__ == "__main__":
    main()
