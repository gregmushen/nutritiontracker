from app.models.food import NutrientsPer100

NUTRIENT_FIELDS = list(NutrientsPer100.model_fields.keys())


def compute_recipe_nutrients(
    ingredients: list[dict], total_weight_g: float, servings: float
) -> tuple[dict, dict]:
    totals: dict[str, float | None] = {f: 0.0 for f in NUTRIENT_FIELDS}
    for ing in ingredients:
        snapshot = ing["food_snapshot"]
        grams = ing["grams"]
        for f in NUTRIENT_FIELDS:
            per_100 = snapshot.get(f)
            if per_100 is None:
                totals[f] = None
            elif totals[f] is not None:
                totals[f] += per_100 * grams / 100

    per_100 = {
        f: None if totals[f] is None else round(totals[f] * 100 / total_weight_g, 2)
        for f in NUTRIENT_FIELDS
    }
    per_serving = {
        f: None if totals[f] is None else round(totals[f] / servings, 2)
        for f in NUTRIENT_FIELDS
    }
    return per_100, per_serving
