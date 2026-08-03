from app.services.recipe_nutrition import compute_recipe_nutrients


def test_recipe_nutrients():
    ingredients = [
        {"grams": 100, "food_snapshot": {"calories_kcal": 350, "protein_g": 12, "carbs_g": 60, "fat_g": 6}},
        {"grams": 200, "food_snapshot": {"calories_kcal": 60, "protein_g": 3, "carbs_g": 5, "fat_g": 3}},
    ]
    total_weight_g = 300
    servings = 2

    per_100, per_serving = compute_recipe_nutrients(ingredients, total_weight_g, servings)

    # Total: oats=350cal*1 + milk=60cal*2 = 470 cal
    # Per 100g: 470/300*100 = 156.67
    assert abs(per_100["calories_kcal"] - 156.67) < 0.1
    # Per serving: 470/2 = 235
    assert abs(per_serving["calories_kcal"] - 235) < 0.1


def test_recipe_nutrients_preserve_unknown_and_measured_zero():
    ingredients = [
        {
            "grams": 100,
            "food_snapshot": {"protein_g": 0, "vitamin_k_ug": None},
        }
    ]

    per_100, per_serving = compute_recipe_nutrients(
        ingredients, total_weight_g=100, servings=1
    )

    assert per_100["protein_g"] == per_serving["protein_g"] == 0
    assert per_100["vitamin_k_ug"] is None
    assert per_serving["vitamin_k_ug"] is None
