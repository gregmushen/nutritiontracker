from app.database import init_schema


def test_schema_includes_expanded_nutrients():
    import sqlite3

    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(foods)")}
    conn.close()

    assert {"caffeine_mg", "riboflavin_mg", "biotin_ug", "chromium_ug"} <= columns


def test_init_schema_repairs_old_private_food_indexes():
    import sqlite3

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    conn.execute("DROP INDEX idx_foods_shared_source_code_unique")
    conn.execute("DROP INDEX idx_foods_owned_source_code_unique")
    conn.execute(
        """CREATE UNIQUE INDEX idx_foods_source_code_unique
           ON foods(source, source_code) WHERE source_code IS NOT NULL"""
    )
    food_id = conn.execute(
        """INSERT INTO foods (source, source_code, name, owner_user_id)
           VALUES ('recipe', 'legacy', 'Legacy recipe', NULL)"""
    ).lastrowid
    conn.commit()

    init_schema(conn)

    owner = conn.execute(
        "SELECT owner_user_id FROM foods WHERE id = ?", (food_id,)
    ).fetchone()["owner_user_id"]
    indexes = {
        row["name"] for row in conn.execute("PRAGMA index_list(foods)").fetchall()
    }
    conn.close()
    assert owner == 1
    assert "idx_foods_source_code_unique" not in indexes
    assert "idx_foods_shared_source_code_unique" in indexes
    assert "idx_foods_owned_source_code_unique" in indexes


def test_init_schema_merges_private_food_ownership_collisions():
    import json
    import sqlite3

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    legacy_id = conn.execute(
        """INSERT INTO foods
           (source, source_code, name, owner_user_id)
           VALUES ('nccdb', '123', 'Legacy', NULL)"""
    ).lastrowid
    owned_id = conn.execute(
        """INSERT INTO foods
           (source, source_code, name, owner_user_id)
           VALUES ('nccdb', '123', 'Owned', 1)"""
    ).lastrowid
    conn.execute(
        """INSERT INTO diary_entries
           (date, meal_type, food_id, food_snapshot, food_name, amount, unit,
            grams, nutrients_total)
           VALUES ('2026-08-02', 'lunch', ?, '{}', 'Legacy', 100, 'g', 100, '{}')""",
        (legacy_id,),
    )
    conn.execute(
        """INSERT INTO recipes
           (name, servings, total_weight_g, ingredients,
            nutrients_per_100, nutrients_per_serving)
           VALUES ('Recipe', 1, 100, ?, '{}', '{}')""",
        (
            json.dumps(
                [
                    {
                        "food_id": legacy_id,
                        "food_snapshot": {"name": "Legacy"},
                        "amount": 100,
                        "unit": "g",
                        "grams": 100,
                    }
                ]
            ),
        ),
    )
    conn.commit()

    init_schema(conn)

    foods = conn.execute(
        "SELECT id, owner_user_id FROM foods WHERE source = 'nccdb'"
    ).fetchall()
    diary_food_id = conn.execute("SELECT food_id FROM diary_entries").fetchone()[0]
    ingredients = json.loads(
        conn.execute("SELECT ingredients FROM recipes").fetchone()[0]
    )
    conn.close()
    assert [tuple(food) for food in foods] == [(owned_id, 1)]
    assert diary_food_id == owned_id
    assert ingredients[0]["food_id"] == owned_id


def test_migration_0008_repairs_existing_personal_data(tmp_path, monkeypatch):
    import json
    import sqlite3
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    database_path = tmp_path / "legacy.db"
    monkeypatch.setenv("NT_DB_PATH", str(database_path))
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    command.upgrade(config, "0007")

    snapshot = {
        "name": "Beer",
        "base_quantity": 100,
        "base_unit": "ml",
        "density_g_per_ml": 0.8,
        "calories_kcal": 30,
        "vitamin_k_ug": None,
    }
    conn = sqlite3.connect(database_path)
    food_id = conn.execute(
        """INSERT INTO foods
           (source, source_code, name, owner_user_id)
           VALUES ('recipe', 'legacy', 'Legacy recipe', NULL)"""
    ).lastrowid
    conn.execute("DROP INDEX idx_foods_shared_source_code_unique")
    conn.execute("DROP INDEX idx_foods_owned_source_code_unique")
    conn.execute(
        """CREATE UNIQUE INDEX idx_foods_source_code_unique
           ON foods(source, source_code) WHERE source_code IS NOT NULL"""
    )
    conn.execute(
        """INSERT INTO diary_entries
           (date, meal_type, food_id, food_snapshot, food_name, amount, unit,
            grams, nutrients_total)
           VALUES ('2026-08-02', 'dinner', ?, ?, 'Beer', 100, 'ml', 80, ?)""",
        (
            food_id,
            json.dumps(snapshot),
            json.dumps({"calories_kcal": 24, "vitamin_k_ug": 0}),
        ),
    )
    conn.execute(
        """INSERT INTO recipes
           (name, servings, total_weight_g, ingredients,
            nutrients_per_100, nutrients_per_serving)
           VALUES ('Drink', 1, 80, ?, ?, ?)""",
        (
            json.dumps(
                [
                    {
                        "food_id": food_id,
                        "food_snapshot": snapshot,
                        "amount": 100,
                        "unit": "ml",
                        "grams": 80,
                    }
                ]
            ),
            json.dumps({"calories_kcal": 24, "vitamin_k_ug": 0}),
            json.dumps({"calories_kcal": 24, "vitamin_k_ug": 0}),
        ),
    )
    conn.commit()
    conn.close()

    command.upgrade(config, "head")

    conn = sqlite3.connect(database_path)
    conn.row_factory = sqlite3.Row
    owner = conn.execute(
        "SELECT owner_user_id FROM foods WHERE id = ?", (food_id,)
    ).fetchone()["owner_user_id"]
    diary = json.loads(
        conn.execute("SELECT nutrients_total FROM diary_entries").fetchone()[0]
    )
    recipe = conn.execute(
        "SELECT ingredients, nutrients_per_serving FROM recipes"
    ).fetchone()
    ingredients = json.loads(recipe["ingredients"])
    per_serving = json.loads(recipe["nutrients_per_serving"])
    revision = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    conn.close()
    assert owner == 1
    assert diary["calories_kcal"] == 30
    assert diary["vitamin_k_ug"] is None
    assert ingredients[0]["base_amount"] == 100
    assert per_serving["calories_kcal"] == 30
    assert per_serving["vitamin_k_ug"] is None
    assert revision == "0008"


def test_migration_0008_merges_private_food_ownership_collisions(
    tmp_path, monkeypatch
):
    import json
    import sqlite3
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    database_path = tmp_path / "legacy.db"
    monkeypatch.setenv("NT_DB_PATH", str(database_path))
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    command.upgrade(config, "0007")

    conn = sqlite3.connect(database_path)
    conn.execute(
        """INSERT INTO food_sources
           (code, label, publisher, tier, license)
           VALUES ('nccdb', 'NCCDB', 'NCC', 1, 'Private')"""
    )
    legacy_id = conn.execute(
        """INSERT INTO foods
           (source, source_code, name, owner_user_id)
           VALUES ('nccdb', '123', 'Legacy', NULL)"""
    ).lastrowid
    owned_id = conn.execute(
        """INSERT INTO foods
           (source, source_code, name, owner_user_id)
           VALUES ('nccdb', '123', 'Owned', 1)"""
    ).lastrowid
    conn.execute(
        """INSERT INTO diary_entries
           (date, meal_type, food_id, food_snapshot, food_name, amount, unit,
            grams, nutrients_total)
           VALUES ('2026-08-02', 'lunch', ?, '{}', 'Legacy', 100, 'g', 100, '{}')""",
        (legacy_id,),
    )
    conn.execute(
        """INSERT INTO recipes
           (name, servings, total_weight_g, ingredients,
            nutrients_per_100, nutrients_per_serving)
           VALUES ('Recipe', 1, 100, ?, '{}', '{}')""",
        (
            json.dumps(
                [
                    {
                        "food_id": legacy_id,
                        "food_snapshot": {"name": "Legacy"},
                        "amount": 100,
                        "unit": "g",
                        "grams": 100,
                    }
                ]
            ),
        ),
    )
    conn.commit()
    conn.close()

    command.upgrade(config, "head")

    conn = sqlite3.connect(database_path)
    foods = conn.execute(
        "SELECT id, owner_user_id FROM foods WHERE source = 'nccdb'"
    ).fetchall()
    diary_food_id = conn.execute("SELECT food_id FROM diary_entries").fetchone()[0]
    ingredients = json.loads(
        conn.execute("SELECT ingredients FROM recipes").fetchone()[0]
    )
    conn.close()
    assert foods == [(owned_id, 1)]
    assert diary_food_id == owned_id
    assert ingredients[0]["food_id"] == owned_id
