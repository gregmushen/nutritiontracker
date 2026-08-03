from app.providers.food_data_central import normalize_usda_food


def test_normalize_usda_food():
    raw = {
        "fdcId": 12345,
        "description": "Banana, raw",
        "brandName": None,
        "gtinUpc": "",
        "foodNutrients": [
            {"nutrientId": 1008, "value": 89},   # Energy
            {"nutrientId": 1003, "value": 1.1},   # Protein
            {"nutrientId": 1005, "value": 22.8},  # Carbs
            {"nutrientId": 1004, "value": 0.3},   # Fat
            {"nutrientId": 1057, "value": 1.2},   # Caffeine
            {"nutrientId": 1166, "value": 0.07},  # Riboflavin
            {"nutrientId": 1176, "value": 0.2},   # Biotin
            {"nutrientId": 1103, "value": 1.1},   # Selenium
        ],
    }
    food = normalize_usda_food(raw)
    assert food["name"] == "Banana, raw"
    assert food["source"] == "food_data_central"
    assert food["source_code"] == "12345"
    assert food["calories_kcal"] == 89
    assert food["protein_g"] == 1.1
    assert food["caffeine_mg"] == 1.2
    assert food["riboflavin_mg"] == 0.07
    assert food["biotin_ug"] == 0.2
    assert food["selenium_ug"] == 1.1


def test_normalize_handles_missing_nutrients():
    raw = {
        "fdcId": 99,
        "description": "Mystery food",
        "foodNutrients": [],
    }
    food = normalize_usda_food(raw)
    assert food["calories_kcal"] is None


def test_normalize_keeps_measured_zero():
    """An analysed zero must stay 0 so it is distinguishable from unknown."""
    raw = {
        "fdcId": 100,
        "description": "Vegetable oil",
        "foodNutrients": [
            {"nutrient": {"id": 1003}, "amount": 0},
            {"nutrient": {"id": 1004}, "amount": 100},
        ],
    }
    food = normalize_usda_food(raw)
    assert food["protein_g"] == 0
    assert food["fat_g"] == 100
    assert food["vitamin_k_ug"] is None
    assert food["protein_g"] == 0


def test_normalize_supports_foundation_energy_ids_with_precedence():
    raw = {
        "fdcId": 100,
        "description": "Foundation food",
        "foodNutrients": [
            {"nutrient": {"id": 1008}, "amount": 90},
            {"nutrient": {"id": 2047}, "amount": 80},
            {"nutrient": {"id": 2048}, "amount": 85},
        ],
    }

    food = normalize_usda_food(raw)

    assert food["calories_kcal"] == 90


def test_normalize_detects_fndds_from_data_type():
    raw = {
        "fdcId": 321,
        "dataType": "Survey (FNDDS)",
        "description": "Milk, whole",
        "foodNutrients": [{"nutrient": {"id": 1003}, "amount": 3.2}],
    }
    assert normalize_usda_food(raw)["source"] == "usda_fndds"


def test_normalize_detects_each_usda_dataset():
    cases = {
        "Survey (FNDDS)": "usda_fndds",
        "Foundation": "usda_foundation",
        "SR Legacy": "usda_sr_legacy",
        "Branded": "usda_branded",
    }
    for data_type, expected in cases.items():
        raw = {"fdcId": 1, "dataType": data_type, "description": "x"}
        assert normalize_usda_food(raw)["source"] == expected


def test_normalize_falls_back_to_generic_source():
    raw = {"fdcId": 1, "description": "No dataType here"}
    assert normalize_usda_food(raw)["source"] == "food_data_central"


def test_explicit_source_overrides_data_type():
    raw = {"fdcId": 1, "dataType": "Foundation", "description": "x"}
    assert normalize_usda_food(raw, source="usda_fndds")["source"] == "usda_fndds"


def test_normalize_reads_fndds_portion():
    raw = {
        "fdcId": 5,
        "dataType": "Survey (FNDDS)",
        "description": "Milk, whole",
        "foodNutrients": [],
        "foodPortions": [{"portionDescription": "1 cup", "gramWeight": 244}],
    }
    food = normalize_usda_food(raw)
    assert food["serving_quantity"] == 244
    assert food["serving_unit"] == "g"
    assert food["serving_size_text"] == "1 cup"


def test_normalize_reads_sr_legacy_portion():
    raw = {
        "fdcId": 6,
        "dataType": "SR Legacy",
        "description": "Banana, raw",
        "foodNutrients": [],
        "foodPortions": [
            {"amount": 1, "gramWeight": 118, "modifier": "cup, sliced"},
        ],
    }
    food = normalize_usda_food(raw)
    assert food["serving_quantity"] == 118
    assert food["serving_size_text"] == "1 cup, sliced"


def test_normalize_skips_unusable_portions():
    raw = {
        "fdcId": 7,
        "description": "Something",
        "foodNutrients": [],
        "foodPortions": [
            {"portionDescription": "Quantity not specified", "gramWeight": 100},
            {"portionDescription": "1 tbsp", "gramWeight": 14},
        ],
    }
    food = normalize_usda_food(raw)
    assert food["serving_quantity"] == 14
    assert food["serving_size_text"] == "1 tbsp"


def test_normalize_without_portions_leaves_serving_unset():
    raw = {"fdcId": 8, "description": "Plain", "foodNutrients": []}
    food = normalize_usda_food(raw)
    assert food["serving_quantity"] is None
    assert food["serving_unit"] is None
