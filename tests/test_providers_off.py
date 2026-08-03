import pytest

from app.providers.open_food_facts import normalize_off_food


def test_normalize_off_food():
    raw = {
        "code": "3017620422003",
        "product_name": "Nutella",
        "brands": "Ferrero",
        "image_url": "https://example.com/nutella.jpg",
        "serving_quantity": "15",
        "serving_size": "15 g",
        "ingredients_text": "Sugar, hazelnuts",
        "allergens_tags": ["en:milk", "en:nuts"],
        "ingredients_analysis_tags": ["en:vegetarian"],
        "categories_tags": ["en:spreads"],
        "labels_tags": ["en:gluten-free"],
        "countries_tags": ["en:united-states"],
        "nutriscore_grade": "e",
        "nova_group": 4,
        "product_quantity": "350",
        "product_quantity_unit": "g",
        "nutriments": {
            "energy-kcal_100g": 539,
            "proteins_100g": 6.3,
            "carbohydrates_100g": 57.5,
            "fat_100g": 30.9,
            "sugars_100g": 56.3,
            "saturated-fat_100g": 10.6,
            "fiber_100g": 3.4,
            "sodium_100g": 0.041,
            "calcium_100g": 120,
            "calcium_unit": "mg",
            "caffeine_100g": 0.056338,
            "caffeine_unit": "g",
            "vitamin-pp_100g": 5.6338,
            "vitamin-pp_unit": "mg",
            "vitamin-c_100g": 16.9,
            "vitamin-c_unit": "mg",
        },
    }
    food = normalize_off_food(raw)
    assert food["name"] == "Nutella"
    assert food["brand"] == "Ferrero"
    assert food["source"] == "open_food_facts"
    assert food["barcode"] == "3017620422003"
    assert food["calories_kcal"] == 539
    assert food["protein_g"] == 6.3
    assert food["sodium_mg"] == 41  # 0.041g * 1000
    assert food["calcium_mg"] == 120
    assert food["caffeine_mg"] == 56.338
    assert food["niacin_mg"] == 5.6338
    assert food["vitamin_c_mg"] == 16.9
    assert food["ingredients_text"] == "Sugar, hazelnuts"
    assert food["allergens_tags"] == ["en:milk", "en:nuts"]
    assert food["dietary_tags"] == ["en:vegetarian"]
    assert food["nutriscore_grade"] == "e"
    assert food["nova_group"] == 4
    assert food["product_quantity"] == 350


def test_normalize_handles_missing_fields():
    raw = {
        "code": "000",
        "product_name": "Blank",
        "nutriments": {},
    }
    food = normalize_off_food(raw)
    assert food["calories_kcal"] == 0


def test_normalize_falls_back_to_the_unit_off_stores():
    """Without an explicit `_unit`, per-100g figures are read as OFF stores them.

    OFF normalizes every nutrient to grams (energy to kcal), so a bare
    `calcium_100g` is grams and has to be scaled up to milligrams.
    """
    food = normalize_off_food(
        {
            "code": "000",
            "product_name": "Bare",
            "nutriments": {
                "energy-kcal_100g": 539,
                "calcium_100g": 0.0140845,
                "vitamin-d_100g": 0.0000025,
                "salt_unit": None,
                "sodium_100g": 0.041,
                "sodium_unit": "",
            },
        }
    )
    assert food["calories_kcal"] == 539
    assert food["calcium_mg"] == pytest.approx(14.0845)
    assert food["vitamin_d_ug"] == pytest.approx(2.5)
    assert food["sodium_mg"] == pytest.approx(41)
