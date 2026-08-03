from app.models.food import NutrientsPer100


def compute_entry_nutrients(food: dict, grams: float) -> dict:
    nutrient_fields = list(NutrientsPer100.model_fields.keys())
    result = {}
    for field in nutrient_fields:
        per_100 = food.get(field)
        result[field] = (
            None if per_100 is None else round(per_100 * grams / 100, 2)
        )
    return result


def build_food_snapshot(food: dict) -> dict:
    exclude = {"created_at", "updated_at"}
    return {k: v for k, v in food.items() if k not in exclude}
