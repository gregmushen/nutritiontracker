import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from app.database import get_connection
from app.providers.open_food_facts import normalize_off_food
from scripts.import_off_parquet import import_off_parquet, parquet_row_to_off_product


def test_parquet_row_converts_nested_names_and_nutrients():
    product = parquet_row_to_off_product(
        {
            "code": "0889392000863",
            "product_name": [{"lang": "de", "text": "Celsius"}, {"lang": "en", "text": "Celsius Energy"}],
            "brands": "Celsius",
            "allergens_tags": ["en:milk"],
            "ingredients_analysis_tags": ["en:vegan"],
            "categories_tags": ["en:energy-drinks"],
            "labels_tags": ["en:gluten-free"],
            "countries_tags": ["en:united-states"],
            "ingredients_text": [{"lang": "en", "text": "Water, caffeine"}],
            "nutriscore_grade": "c",
            "nova_group": 4,
            "product_quantity": "355",
            "product_quantity_unit": "ml",
            "nutriments": [
                {"name": "caffeine", "100g": 0.056338, "unit": "g"},
                {"name": "vitamin-pp", "100g": 0.0056338, "unit": "mg"},
            ],
        }
    )

    assert product["product_name"] == "Celsius Energy"
    assert product["nutriments"]["caffeine_100g"] == 0.056338
    # The dump's `unit` describes `value`/`serving`, not the normalized `100g`,
    # so it must not be forwarded as an override.
    assert "vitamin-pp_unit" not in product["nutriments"]
    assert product["allergens_tags"] == ["en:milk"]
    assert product["ingredients_text"] == "Water, caffeine"


def test_import_filters_country_and_normalizes_nutrients(tmp_path):
    source_path = tmp_path / "food.parquet"
    database_path = tmp_path / "nutrition.db"
    rows = [
        {
            "code": "0889392000863",
            "product_name": [{"lang": "en", "text": "Celsius Energy"}],
            "brands": "Celsius",
            "allergens_tags": ["en:milk"],
            "ingredients_analysis_tags": ["en:vegan"],
            "categories_tags": ["en:energy-drinks"],
            "labels_tags": ["en:gluten-free"],
            "countries_tags": ["en:united-states"],
            "ingredients_text": [{"lang": "en", "text": "Water, caffeine"}],
            "nutriscore_grade": "c",
            "nova_group": 4,
            "product_quantity": "355",
            "product_quantity_unit": "ml",
            "serving_quantity": "355",
            "serving_size": "355 ml",
            "nutriments": [
                {
                    "name": "caffeine",
                    "value": None,
                    "100g": 0.056338,
                    "serving": None,
                    "unit": "g",
                    "prepared_value": None,
                    "prepared_100g": None,
                    "prepared_serving": None,
                    "prepared_unit": None,
                },
                {
                    "name": "vitamin-pp",
                    "value": None,
                    "100g": 0.0056338,
                    "serving": None,
                    "unit": "mg",
                    "prepared_value": None,
                    "prepared_100g": None,
                    "prepared_serving": None,
                    "prepared_unit": None,
                },
            ],
        },
        {
            "code": "0000000000000",
            "product_name": [{"lang": "en", "text": "German product"}],
            "brands": "Example",
            "allergens_tags": [],
            "ingredients_analysis_tags": [],
            "categories_tags": [],
            "labels_tags": [],
            "countries_tags": ["en:germany"],
            "ingredients_text": [],
            "nutriscore_grade": None,
            "nova_group": None,
            "product_quantity": None,
            "product_quantity_unit": None,
            "serving_quantity": None,
            "serving_size": None,
            "nutriments": [],
        },
    ]
    pq.write_table(pa.Table.from_pylist(rows), source_path)

    import_off_parquet(
        str(source_path), str(database_path), country="en:united-states"
    )

    conn = get_connection(database_path)
    foods = conn.execute(
        """SELECT name, caffeine_mg, niacin_mg, ingredients_text, allergens_tags,
                  dietary_tags, nutriscore_grade, nova_group, product_quantity
           FROM foods ORDER BY id"""
    ).fetchall()
    conn.close()
    assert len(foods) == 1
    food = foods[0]
    assert food["name"] == "Celsius Energy"
    assert food["caffeine_mg"] == pytest.approx(56.338)
    # 0.0056338 g stored per 100 g, despite the row's `unit` reading "mg".
    assert food["niacin_mg"] == pytest.approx(5.6338)
    assert (
        food["ingredients_text"],
        food["allergens_tags"],
        food["dietary_tags"],
        food["nutriscore_grade"],
        food["nova_group"],
        food["product_quantity"],
    ) == ("Water, caffeine", '["en:milk"]', '["en:vegan"]', "c", 4, 355.0)


def test_null_unit_does_not_abort_the_import():
    """A null `unit` used to raise AttributeError and kill the whole run."""
    product = parquet_row_to_off_product(
        {
            "code": "1",
            "product_name": [{"lang": "en", "text": "X"}],
            "nutriments": [{"name": "calcium", "100g": 0.012, "unit": None}],
        }
    )

    food = normalize_off_food(product)
    assert food["calcium_mg"] == pytest.approx(12.0)


def test_import_rejects_missing_required_columns(tmp_path):
    source_path = tmp_path / "missing-code.parquet"
    pq.write_table(
        pa.Table.from_pylist(
            [{"product_name": [{"lang": "en", "text": "No identity"}]}]
        ),
        source_path,
    )

    with pytest.raises(ValueError, match=r"code, nutriments"):
        import_off_parquet(str(source_path), str(tmp_path / "nutrition.db"))


def test_reimport_preserves_metadata_when_optional_column_is_absent(tmp_path):
    source_path = tmp_path / "full.parquet"
    database_path = tmp_path / "nutrition.db"
    pq.write_table(
        pa.Table.from_pylist(
            [
                {
                    "code": "123",
                    "product_name": [{"lang": "en", "text": "Original"}],
                    "allergens_tags": ["en:milk"],
                    "nutriments": [],
                }
            ]
        ),
        source_path,
    )
    import_off_parquet(str(source_path), str(database_path))

    update_path = tmp_path / "without-metadata.parquet"
    pq.write_table(
        pa.Table.from_pylist(
            [
                {
                    "code": "123",
                    "product_name": [{"lang": "en", "text": "Updated"}],
                    "nutriments": [],
                }
            ]
        ),
        update_path,
    )
    import_off_parquet(str(update_path), str(database_path))

    conn = get_connection(database_path)
    food = conn.execute(
        "SELECT name, allergens_tags FROM foods WHERE source_code = '123'"
    ).fetchone()
    conn.close()
    assert food["name"] == "Updated"
    assert food["allergens_tags"] == '["en:milk"]'
