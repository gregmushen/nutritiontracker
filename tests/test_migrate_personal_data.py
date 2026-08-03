import json
import sqlite3

from app.database import init_schema
from scripts.migrate_personal_data import migrate_personal_data


def _connection(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    return conn


def _insert_food(conn, *, source, source_code, name):
    return conn.execute(
        """INSERT INTO foods (source, source_code, name, calories_kcal)
           VALUES (?, ?, ?, 100)""",
        (source, source_code, name),
    ).lastrowid


def test_migrates_personal_records_and_remaps_diary_foods(tmp_path):
    source_path = tmp_path / "source.db"
    target_path = tmp_path / "target.db"
    source = _connection(source_path)
    source_catalog_food = _insert_food(
        source, source="food_data_central", source_code="fdc-1", name="Catalog food"
    )
    source_custom_food = _insert_food(
        source, source="custom", source_code=None, name="Custom food"
    )
    for food_id, name in (
        (source_catalog_food, "Catalog food"),
        (source_custom_food, "Custom food"),
    ):
        source.execute(
            """INSERT INTO diary_entries
               (date, meal_type, food_id, food_snapshot, food_name, amount, unit, grams, nutrients_total)
               VALUES ('2026-08-01', 'breakfast', ?, ?, ?, 1, 'g', 100, ?)""",
            (
                food_id,
                json.dumps({"name": name, "calories_kcal": 100}),
                name,
                json.dumps({"calories_kcal": 100}),
            ),
        )
    source.execute(
        "INSERT INTO journal_entries (date, body) VALUES ('2026-08-01', 'Preserve me')"
    )
    source.commit()
    source.close()

    target = _connection(target_path)
    _insert_food(target, source="custom", source_code=None, name="Unrelated custom food")
    target_catalog_food = _insert_food(
        target, source="food_data_central", source_code="fdc-1", name="Catalog food"
    )
    target.commit()
    target.close()

    copied = migrate_personal_data(source_path, target_path)

    assert copied["diary_entries"] == 2
    assert copied["journal_entries"] == 1
    target = sqlite3.connect(target_path)
    target.row_factory = sqlite3.Row
    rows = target.execute(
        "SELECT food_id, food_name FROM diary_entries ORDER BY id"
    ).fetchall()
    custom_food = target.execute(
        "SELECT id FROM foods WHERE source = 'custom' AND name = 'Custom food'"
    ).fetchone()
    journal = target.execute("SELECT body FROM journal_entries").fetchone()
    target.close()

    assert rows[0]["food_id"] == target_catalog_food
    assert rows[1]["food_id"] == custom_food["id"]
    assert journal["body"] == "Preserve me"


def test_migrates_accounts_and_preserves_their_ids(tmp_path):
    """Diary rows and owned foods point at users by id, so ids must survive.

    The target is freshly built and already carries a seeded default account,
    so the incoming ids collide and the source has to win.
    """
    source_path = tmp_path / "source.db"
    target_path = tmp_path / "target.db"
    source = _connection(source_path)
    target = _connection(target_path)

    source.execute("DELETE FROM users")
    source.execute(
        "INSERT INTO users (id, name, token_hash) VALUES (1, 'Primary', NULL)"
    )
    source.execute(
        "INSERT INTO users (id, name, token_hash) VALUES (2, 'Second', 'hashed')"
    )
    food_id = _insert_food(
        source, source="food_data_central", source_code="fdc-1", name="Catalog food"
    )
    source.execute(
        """INSERT INTO diary_entries
           (user_id, date, meal_type, food_id, food_snapshot, food_name, amount, unit, grams, nutrients_total)
           VALUES (2, '2026-08-01', 'breakfast', ?, ?, 'Catalog food', 1, 'g', 100, ?)""",
        (food_id, json.dumps({"name": "Catalog food"}), json.dumps({"calories_kcal": 100})),
    )
    source.commit()

    _insert_food(
        target, source="food_data_central", source_code="fdc-1", name="Catalog food"
    )
    target.commit()
    target.close()
    source.close()

    copied = migrate_personal_data(source_path, target_path)
    assert copied["users"] == 2

    check = sqlite3.connect(target_path)
    check.row_factory = sqlite3.Row
    users = {row["id"]: row["name"] for row in check.execute("SELECT id, name FROM users")}
    assert users[1] == "Primary"
    assert users[2] == "Second"

    entry = check.execute("SELECT user_id FROM diary_entries").fetchone()
    assert entry["user_id"] == 2
    check.close()


def test_remaps_recipe_ingredient_food_ids(tmp_path):
    source_path = tmp_path / "source.db"
    target_path = tmp_path / "target.db"
    source = _connection(source_path)
    source_food = _insert_food(
        source, source="custom", source_code=None, name="Recipe ingredient"
    )
    source.execute(
        """UPDATE foods SET owner_user_id = 1 WHERE id = ?""", (source_food,)
    )
    source.execute(
        """INSERT INTO recipes
           (name, servings, total_weight_g, ingredients,
            nutrients_per_100, nutrients_per_serving)
           VALUES ('Soup', 2, 500, ?, '{}', '{}')""",
        (
            json.dumps(
                [
                    {
                        "food_id": source_food,
                        "food_snapshot": {"name": "Recipe ingredient"},
                        "amount": 100,
                        "unit": "g",
                        "grams": 100,
                    }
                ]
            ),
        ),
    )
    source.commit()
    source.close()

    target = _connection(target_path)
    _insert_food(target, source="custom", source_code=None, name="ID collision")
    target.commit()
    target.close()

    migrate_personal_data(source_path, target_path)

    check = sqlite3.connect(target_path)
    check.row_factory = sqlite3.Row
    ingredients = json.loads(
        check.execute("SELECT ingredients FROM recipes").fetchone()["ingredients"]
    )
    mapped_id = ingredients[0]["food_id"]
    mapped_food = check.execute(
        "SELECT name FROM foods WHERE id = ?", (mapped_id,)
    ).fetchone()
    check.close()
    assert mapped_id != source_food
    assert mapped_food["name"] == "Recipe ingredient"


def test_maps_legacy_usda_reference_to_dataset_specific_target(tmp_path):
    source_path = tmp_path / "source.db"
    target_path = tmp_path / "target.db"
    source = _connection(source_path)
    legacy_id = _insert_food(
        source, source="food_data_central", source_code="123", name="Legacy"
    )
    source.execute(
        """INSERT INTO diary_entries
           (date, meal_type, food_id, food_snapshot, food_name, amount, unit,
            grams, nutrients_total)
           VALUES ('2026-08-01', 'lunch', ?, '{}', 'Legacy', 100, 'g', 100, '{}')""",
        (legacy_id,),
    )
    source.commit()
    source.close()

    target = _connection(target_path)
    refreshed_id = _insert_food(
        target, source="usda_foundation", source_code="123", name="Refreshed"
    )
    target.commit()
    target.close()

    migrate_personal_data(source_path, target_path)

    check = sqlite3.connect(target_path)
    entry_food_id = check.execute(
        "SELECT food_id FROM diary_entries"
    ).fetchone()[0]
    count = check.execute(
        "SELECT COUNT(*) FROM foods WHERE source_code = '123'"
    ).fetchone()[0]
    check.close()
    assert entry_food_id == refreshed_id
    assert count == 1


def test_copies_owned_foods_even_when_no_diary_references_them(tmp_path):
    source_path = tmp_path / "source.db"
    target_path = tmp_path / "target.db"
    source = _connection(source_path)
    food_id = _insert_food(
        source, source="custom", source_code="private", name="Private"
    )
    source.execute("UPDATE foods SET owner_user_id = 1 WHERE id = ?", (food_id,))
    source.commit()
    source.close()
    target = _connection(target_path)
    target.close()

    migrate_personal_data(source_path, target_path)

    check = sqlite3.connect(target_path)
    row = check.execute(
        "SELECT name, owner_user_id FROM foods WHERE source_code = 'private'"
    ).fetchone()
    check.close()
    assert row == ("Private", 1)
