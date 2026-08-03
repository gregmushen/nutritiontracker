import pytest

from app.models.diary import DiaryEntryCreate
from app.models.food import FoodCreate, NutrientsPer100
from app.models.recipe import RecipeCreate, RecipeIngredientInput
from app.models.weight import WeightEntryCreate


def test_nutrients_default_to_unknown():
    """Unset nutrients are None (not measured), never 0 (measured as zero)."""
    n = NutrientsPer100()
    assert n.calories_kcal is None
    assert n.protein_g is None
    assert n.niacin_mg is None
    assert n.caffeine_mg is None
    assert n.riboflavin_mg is None


def test_nutrients_keep_explicit_zero():
    n = NutrientsPer100(calories_kcal=0, protein_g=1.5)
    assert n.calories_kcal == 0
    assert n.protein_g == 1.5
    assert n.fiber_g is None


def test_food_create_minimal():
    f = FoodCreate(name="Banana", source="custom")
    assert f.name == "Banana"
    assert f.brand is None


def test_food_create_rejects_invalid_source():
    with pytest.raises(ValueError):
        FoodCreate(name="X", source="invalid")


@pytest.mark.parametrize(
    "field",
    (
        {"base_quantity": 0},
        {"base_quantity": -1},
        {"base_unit": "oz"},
        {"density_g_per_ml": 0},
        {"density_g_per_ml": -1},
        {"base_quantity": float("inf")},
        {"density_g_per_ml": float("inf")},
    ),
)
def test_food_create_rejects_invalid_base_measurements(field):
    with pytest.raises(ValueError):
        FoodCreate(name="Invalid", **field)


def test_diary_entry_create():
    e = DiaryEntryCreate(food_id=1, amount=1.5, unit="cup", meal_type="breakfast")
    assert e.meal_type == "breakfast"


def test_diary_entry_rejects_invalid_meal_type():
    with pytest.raises(ValueError):
        DiaryEntryCreate(food_id=1, amount=1, unit="g", meal_type="brunch")


def test_recipe_create():
    r = RecipeCreate(
        name="Oatmeal",
        servings=2,
        total_weight_g=400,
        ingredients=[
            RecipeIngredientInput(food_id=1, amount=100, unit="g"),
            RecipeIngredientInput(food_id=2, amount=200, unit="ml"),
        ],
    )
    assert len(r.ingredients) == 2


def test_weight_entry_create():
    w = WeightEntryCreate(weight_kg=85.5, date="2026-05-19")
    assert w.weight_kg == 85.5
