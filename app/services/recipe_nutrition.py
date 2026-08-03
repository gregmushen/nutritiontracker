from app.models.food import NutrientsPer100

NUTRIENT_FIELDS = list(NutrientsPer100.model_fields.keys())


def compute_recipe_nutrients(
    ingredients: list[dict], total_weight_g: float, servings: float
) -> tuple[dict, dict]:
    totals: dict[str, float | None] = {f: 0.0 for f in NUTRIENT_FIELDS}
    for ing in ingredients:
        snapshot = ing["food_snapshot"]
        base_quantity = snapshot.get("base_quantity", 100)
        if base_quantity is None or base_quantity <= 0:
            raise ValueError("food base_quantity must be greater than zero")
        base_amount = ing.get("base_amount")
        if base_amount is None:
            if snapshot.get("base_unit", "g") == "ml":
                density = snapshot.get("density_g_per_ml")
                if density is None:
                    raise ValueError(
                        "volume-based recipe ingredients require base_amount "
                        "or density_g_per_ml"
                    )
                base_amount = ing["grams"] / density
            else:
                base_amount = ing["grams"]
        for f in NUTRIENT_FIELDS:
            per_100 = snapshot.get(f)
            if per_100 is None:
                totals[f] = None
            elif totals[f] is not None:
                totals[f] += per_100 * base_amount / base_quantity

    per_100 = {
        f: None if totals[f] is None else round(totals[f] * 100 / total_weight_g, 2)
        for f in NUTRIENT_FIELDS
    }
    per_serving = {
        f: None if totals[f] is None else round(totals[f] / servings, 2)
        for f in NUTRIENT_FIELDS
    }
    return per_100, per_serving
