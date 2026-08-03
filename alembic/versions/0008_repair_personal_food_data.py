"""Repair private-food ownership and recompute persisted nutrient totals.

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-02
"""

import json
import os

from alembic import op

from app.services.diary import compute_entry_nutrients
from app.services.food_references import replace_food_references
from app.services.recipe_nutrition import compute_recipe_nutrients
from app.services.unit_conversion import convert_to_grams

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

PRIVATE_SOURCE_CODES = (
    "custom",
    "recipe",
    "cronometer",
    "cronometer_custom",
    "nccdb",
    "crdb",
    "nutritionix",
    "nuttab",
)


def _default_user_id() -> int:
    raw = os.environ.get("NT_DEFAULT_USER_ID", "1")
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f"NT_DEFAULT_USER_ID must be an integer, got {raw!r}") from None
    if value < 1:
        raise ValueError(f"NT_DEFAULT_USER_ID must be a positive rowid, got {value}")
    return value


def _convert_snapshot_amount(
    snapshot: dict, amount: float, unit: str
) -> tuple[float, float]:
    conversion = convert_to_grams(
        amount,
        unit,
        density_g_per_ml=snapshot.get("density_g_per_ml"),
        serving_quantity=snapshot.get("serving_quantity"),
        serving_unit=snapshot.get("serving_unit"),
    )
    return conversion.grams, conversion.amount_in(snapshot.get("base_unit", "g"))


def _repair_diary_totals(connection) -> None:
    rows = connection.exec_driver_sql(
        "SELECT id, amount, unit, food_snapshot FROM diary_entries ORDER BY id"
    ).mappings()
    for row in rows:
        snapshot = json.loads(row["food_snapshot"])
        try:
            grams, base_amount = _convert_snapshot_amount(
                snapshot, row["amount"], row["unit"]
            )
            nutrients = compute_entry_nutrients(snapshot, base_amount)
        except ValueError as error:
            raise ValueError(
                f"Cannot recompute diary entry {row['id']}: {error}"
            ) from error
        connection.exec_driver_sql(
            """UPDATE diary_entries
               SET grams = ?, nutrients_total = ?, updated_at = datetime('now')
               WHERE id = ?""",
            (grams, json.dumps(nutrients), row["id"]),
        )


def _repair_recipe_totals(connection) -> None:
    rows = connection.exec_driver_sql(
        """SELECT id, servings, total_weight_g, ingredients
           FROM recipes ORDER BY id"""
    ).mappings()
    for row in rows:
        ingredients = json.loads(row["ingredients"])
        try:
            for ingredient in ingredients:
                snapshot = ingredient["food_snapshot"]
                grams, base_amount = _convert_snapshot_amount(
                    snapshot, ingredient["amount"], ingredient["unit"]
                )
                ingredient["grams"] = grams
                ingredient["base_amount"] = base_amount
            per_100, per_serving = compute_recipe_nutrients(
                ingredients, row["total_weight_g"], row["servings"]
            )
        except (KeyError, ValueError) as error:
            raise ValueError(f"Cannot recompute recipe {row['id']}: {error}") from error
        connection.exec_driver_sql(
            """UPDATE recipes
               SET ingredients = ?, nutrients_per_100 = ?,
                   nutrients_per_serving = ?, updated_at = datetime('now')
               WHERE id = ?""",
            (
                json.dumps(ingredients),
                json.dumps(per_100),
                json.dumps(per_serving),
                row["id"],
            ),
        )


def upgrade() -> None:
    default_user_id = _default_user_id()
    sources = ", ".join(f"'{source}'" for source in PRIVATE_SOURCE_CODES)
    connection = op.get_bind()
    collisions = connection.exec_driver_sql(
        f"""SELECT legacy.id AS legacy_id, owned.id AS owned_id
            FROM foods legacy
            JOIN foods owned
              ON owned.source = legacy.source
             AND owned.source_code = legacy.source_code
             AND owned.owner_user_id = ?
            WHERE legacy.owner_user_id IS NULL
              AND legacy.source_code IS NOT NULL
              AND legacy.source IN ({sources})""",
        (default_user_id,),
    ).mappings()
    raw_connection = connection.connection.driver_connection
    for collision in list(collisions):
        replace_food_references(
            raw_connection,
            old_food_id=collision["legacy_id"],
            new_food_id=collision["owned_id"],
        )
        raw_connection.execute(
            "DELETE FROM foods WHERE id = ?", (collision["legacy_id"],)
        )

    op.execute(
        f"""UPDATE foods SET owner_user_id = {default_user_id}
            WHERE owner_user_id IS NULL AND source IN ({sources})"""
    )
    op.execute("DROP INDEX IF EXISTS idx_foods_source_code_unique")
    op.execute(
        """CREATE UNIQUE INDEX IF NOT EXISTS idx_foods_shared_source_code_unique
           ON foods(source, source_code)
           WHERE source_code IS NOT NULL AND owner_user_id IS NULL"""
    )
    op.execute(
        """CREATE UNIQUE INDEX IF NOT EXISTS idx_foods_owned_source_code_unique
           ON foods(owner_user_id, source, source_code)
           WHERE source_code IS NOT NULL AND owner_user_id IS NOT NULL"""
    )

    _repair_diary_totals(connection)
    _repair_recipe_totals(connection)


def downgrade() -> None:
    raise NotImplementedError("downgrade not supported for this migration")
