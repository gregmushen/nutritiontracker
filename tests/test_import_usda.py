import json

import pytest

from app.database import get_connection
from scripts.import_usda import import_usda


def test_import_usda_skips_invalid_records(tmp_path):
    source_path = tmp_path / "foundation.json"
    db_path = tmp_path / "nutrition.db"
    source_path.write_text(
        json.dumps(
            {
                "FoundationFoods": [
                    None,
                    {"fdcId": 123, "description": "Test Food", "foodNutrients": []},
                ]
            }
        )
    )

    import_usda(str(source_path), str(db_path))

    conn = get_connection(db_path)
    food = conn.execute("SELECT name FROM foods WHERE source_code = '123'").fetchone()
    conn.close()
    assert food["name"] == "Test Food"


def test_import_usda_adds_missing_foods_from_csv(tmp_path):
    source_path = tmp_path / "foundation.json"
    csv_dir = tmp_path / "csv"
    db_path = tmp_path / "nutrition.db"
    csv_dir.mkdir()
    source_path.write_text(
        json.dumps(
            {
                "FoundationFoods": [
                    {"fdcId": 123, "description": "JSON Food", "foodNutrients": []},
                    None,
                ]
            }
        )
    )
    (csv_dir / "foundation_food.csv").write_text("fdc_id\n123\n456\n")
    (csv_dir / "food.csv").write_text(
        "fdc_id,data_type,description,food_category_id,publication_date\n"
        "123,foundation_food,JSON Food,,2026-04-30\n"
        "456,foundation_food,CSV Fallback Food,,2026-04-30\n"
    )
    (csv_dir / "food_nutrient.csv").write_text(
        "id,fdc_id,nutrient_id,amount\n1,456,2047,42.5\n2,456,1003,2.25\n"
    )

    import_usda(str(source_path), str(db_path), str(csv_dir))

    conn = get_connection(db_path)
    foods = conn.execute(
        "SELECT source_code, name, calories_kcal, protein_g "
        "FROM foods ORDER BY source_code"
    ).fetchall()
    conn.close()
    assert [tuple(food) for food in foods] == [
        ("123", "JSON Food", None, None),
        ("456", "CSV Fallback Food", 42.5, 2.25),
    ]


def test_import_usda_requires_complete_csv_export(tmp_path):
    source_path = tmp_path / "foundation.json"
    csv_dir = tmp_path / "csv"
    csv_dir.mkdir()
    source_path.write_text(json.dumps({"FoundationFoods": []}))

    with pytest.raises(FileNotFoundError, match="foundation_food.csv"):
        import_usda(str(source_path), str(tmp_path / "nutrition.db"), str(csv_dir))


def test_import_fndds_survey_export(tmp_path):
    source_path = tmp_path / "survey.json"
    db_path = tmp_path / "nutrition.db"
    source_path.write_text(
        json.dumps(
            {
                "SurveyFoods": [
                    {
                        "fdcId": 1001,
                        "dataType": "Survey (FNDDS)",
                        "description": "Milk, whole",
                        "foodNutrients": [
                            {"nutrient": {"id": 1008}, "amount": 61},
                            {"nutrient": {"id": 1003}, "amount": 3.27},
                            {"nutrient": {"id": 1185}, "amount": 0.3},
                        ],
                        "foodPortions": [
                            {"portionDescription": "1 cup", "gramWeight": 244}
                        ],
                    }
                ]
            }
        )
    )

    import_usda(str(source_path), str(db_path))

    conn = get_connection(db_path)
    row = conn.execute(
        "SELECT source, source_code, name, calories_kcal, vitamin_k_ug, "
        "caffeine_mg, serving_quantity, serving_size_text FROM foods"
    ).fetchone()
    conn.close()

    assert row["source"] == "usda_fndds"
    assert row["source_code"] == "1001"
    assert row["name"] == "Milk, whole"
    assert row["calories_kcal"] == 61
    assert row["vitamin_k_ug"] == 0.3
    # Not reported by the dataset — unknown, not zero.
    assert row["caffeine_mg"] is None
    assert row["serving_quantity"] == 244
    assert row["serving_size_text"] == "1 cup"


def test_import_tags_sr_legacy_and_foundation_separately(tmp_path):
    db_path = tmp_path / "nutrition.db"

    sr_path = tmp_path / "sr.json"
    sr_path.write_text(
        json.dumps(
            {"SRLegacyFoods": [{"fdcId": 1, "description": "SR Food", "foodNutrients": []}]}
        )
    )
    foundation_path = tmp_path / "foundation.json"
    foundation_path.write_text(
        json.dumps(
            {
                "FoundationFoods": [
                    {"fdcId": 2, "description": "Foundation Food", "foodNutrients": []}
                ]
            }
        )
    )

    import_usda(str(sr_path), str(db_path))
    import_usda(str(foundation_path), str(db_path))

    conn = get_connection(db_path)
    rows = conn.execute("SELECT source, name FROM foods ORDER BY name").fetchall()
    conn.close()

    assert [tuple(r) for r in rows] == [
        ("usda_foundation", "Foundation Food"),
        ("usda_sr_legacy", "SR Food"),
    ]


def test_import_source_override(tmp_path):
    source_path = tmp_path / "food.json"
    db_path = tmp_path / "nutrition.db"
    source_path.write_text(
        json.dumps({"SRLegacyFoods": [{"fdcId": 9, "description": "X", "foodNutrients": []}]})
    )

    import_usda(str(source_path), str(db_path), None, "usda_fndds")

    conn = get_connection(db_path)
    source = conn.execute("SELECT source FROM foods").fetchone()["source"]
    conn.close()
    assert source == "usda_fndds"


def test_reimport_upgrades_legacy_usda_row_in_place(tmp_path):
    source_path = tmp_path / "foundation.json"
    db_path = tmp_path / "nutrition.db"
    source_path.write_text(
        json.dumps(
            {
                "FoundationFoods": [
                    {
                        "fdcId": 123,
                        "description": "Refreshed food",
                        "foodNutrients": [],
                    }
                ]
            }
        )
    )
    conn = get_connection(db_path)
    from app.database import init_schema
    from app.repositories.foods import FoodRepository

    init_schema(conn)
    FoodRepository(conn).ensure_fts()
    legacy_id = conn.execute(
        """INSERT INTO foods
           (source, source_code, name, vitamin_k_ug)
           VALUES ('food_data_central', '123', 'Legacy food', 0)"""
    ).lastrowid
    conn.execute(
        """INSERT INTO diary_entries
           (date, meal_type, food_id, food_snapshot, food_name, amount, unit,
            grams, nutrients_total)
           VALUES ('2026-08-01', 'lunch', ?, '{}', 'Legacy food', 100, 'g',
                   100, '{}')""",
        (legacy_id,),
    )
    conn.commit()
    conn.close()

    import_usda(str(source_path), str(db_path))

    conn = get_connection(db_path)
    foods = conn.execute(
        "SELECT id, source, name, vitamin_k_ug FROM foods WHERE source_code = '123'"
    ).fetchall()
    diary_food_id = conn.execute("SELECT food_id FROM diary_entries").fetchone()[0]
    conn.close()
    assert len(foods) == 1
    assert foods[0]["id"] == diary_food_id == legacy_id
    assert foods[0]["source"] == "usda_foundation"
    assert foods[0]["name"] == "Refreshed food"
    assert foods[0]["vitamin_k_ug"] is None


def test_bare_list_csv_fallback_uses_inferred_dataset_source(tmp_path):
    source_path = tmp_path / "foundation-list.json"
    csv_dir = tmp_path / "csv"
    db_path = tmp_path / "nutrition.db"
    csv_dir.mkdir()
    source_path.write_text(
        json.dumps(
            [
                {
                    "fdcId": 123,
                    "dataType": "Foundation",
                    "description": "JSON Food",
                    "foodNutrients": [],
                }
            ]
        )
    )
    (csv_dir / "foundation_food.csv").write_text("fdc_id\n123\n456\n")
    (csv_dir / "food.csv").write_text(
        "fdc_id,data_type,description\n"
        "123,foundation_food,JSON Food\n"
        "456,foundation_food,CSV Food\n"
    )
    (csv_dir / "food_nutrient.csv").write_text(
        "id,fdc_id,nutrient_id,amount\n1,456,1008,10\n"
    )

    import_usda(str(source_path), str(db_path), str(csv_dir))

    conn = get_connection(db_path)
    sources = {
        row["source"]
        for row in conn.execute("SELECT source FROM foods").fetchall()
    }
    conn.close()
    assert sources == {"usda_foundation"}


def test_reimport_merges_existing_legacy_and_dataset_specific_duplicates(tmp_path):
    source_path = tmp_path / "foundation.json"
    db_path = tmp_path / "nutrition.db"
    source_path.write_text(
        json.dumps(
            {
                "FoundationFoods": [
                    {
                        "fdcId": 123,
                        "description": "Refreshed",
                        "foodNutrients": [],
                    }
                ]
            }
        )
    )
    conn = get_connection(db_path)
    from app.database import init_schema
    from app.repositories.foods import FoodRepository

    init_schema(conn)
    repo = FoodRepository(conn)
    repo.ensure_fts()
    legacy_id = repo.create(
        source="food_data_central",
        source_code="123",
        name="Legacy",
    )
    duplicate_id = repo.create(
        source="usda_foundation",
        source_code="123",
        name="Duplicate",
    )
    for food_id in (legacy_id, duplicate_id):
        conn.execute(
            """INSERT INTO diary_entries
               (date, meal_type, food_id, food_snapshot, food_name, amount,
                unit, grams, nutrients_total)
               VALUES ('2026-08-01', 'lunch', ?, '{}', 'Food', 100, 'g',
                       100, '{}')""",
            (food_id,),
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
                        "food_id": duplicate_id,
                        "food_snapshot": {"name": "Duplicate"},
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

    import_usda(str(source_path), str(db_path))

    conn = get_connection(db_path)
    foods = conn.execute(
        "SELECT id, source, name FROM foods WHERE source_code = '123'"
    ).fetchall()
    diary_ids = {
        row["food_id"] for row in conn.execute("SELECT food_id FROM diary_entries")
    }
    ingredients = json.loads(
        conn.execute("SELECT ingredients FROM recipes").fetchone()["ingredients"]
    )
    conn.close()
    assert [tuple(food) for food in foods] == [
        (legacy_id, "usda_foundation", "Refreshed")
    ]
    assert diary_ids == {legacy_id}
    assert ingredients[0]["food_id"] == legacy_id
