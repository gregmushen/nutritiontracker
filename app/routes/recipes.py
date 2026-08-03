from fastapi import APIRouter, HTTPException, Request

from app.auth import current_user_id
from app.models.recipe import Recipe, RecipeCreate, RecipeUpdate
from app.repositories.foods import FoodRepository
from app.repositories.recipes import RecipeRepository
from app.services.diary import build_food_snapshot
from app.services.recipe_nutrition import compute_recipe_nutrients
from app.services.unit_conversion import convert_to_grams

router = APIRouter(prefix="/recipes", tags=["recipes"])


def _recipe_repo(request: Request) -> RecipeRepository:
    return RecipeRepository(request.app.state.db)


def _food_repo(request: Request) -> FoodRepository:
    return FoodRepository(request.app.state.db)


def _resolve_ingredients(
    food_repo: FoodRepository, ingredients_input: list, user_id: int
) -> list[dict]:
    resolved = []
    for ing in ingredients_input:
        food = food_repo.get(ing.food_id, user_id=user_id)
        if not food:
            raise HTTPException(404, f"Food {ing.food_id} not found")
        conversion = convert_to_grams(
            ing.amount, ing.unit,
            density_g_per_ml=food.get("density_g_per_ml"),
            serving_quantity=food.get("serving_quantity"),
            serving_unit=food.get("serving_unit"),
        )
        resolved.append({
            "food_id": ing.food_id,
            "food_snapshot": build_food_snapshot(food),
            "amount": ing.amount,
            "unit": ing.unit,
            "grams": conversion.grams,
        })
    return resolved


@router.post("", status_code=201, response_model=Recipe, summary="Create recipe")
def create_recipe(request: Request, body: RecipeCreate):
    """Create a recipe from a list of food ingredients. Automatically resolves each ingredient's food record, converts units to grams, and computes per-100g and per-serving nutrient totals."""
    food_repo = _food_repo(request)
    recipe_repo = _recipe_repo(request)

    resolved = _resolve_ingredients(food_repo, body.ingredients, current_user_id(request))
    per_100, per_serving = compute_recipe_nutrients(
        resolved, body.total_weight_g, body.servings
    )

    recipe_id = recipe_repo.create(
        user_id=current_user_id(request),
        name=body.name, servings=body.servings,
        total_weight_g=body.total_weight_g,
        ingredients=resolved,
        nutrients_per_100=per_100,
        nutrients_per_serving=per_serving,
    )
    return recipe_repo.get(recipe_id)


@router.get("", response_model=list[Recipe], summary="List recipes")
def list_recipes(request: Request, limit: int = 20, offset: int = 0):
    """List all recipes, ordered by most recently created."""
    return _recipe_repo(request).list_all(
        user_id=current_user_id(request), limit=limit, offset=offset
    )


@router.get("/{recipe_id}", response_model=Recipe, summary="Get recipe by ID")
def get_recipe(request: Request, recipe_id: int):
    """Get a single recipe by ID."""
    recipe = _recipe_repo(request).get(recipe_id)
    if not recipe or recipe["user_id"] != current_user_id(request):
        raise HTTPException(404, "Recipe not found")
    return recipe


@router.patch("/{recipe_id}", response_model=Recipe, summary="Update recipe")
def update_recipe(request: Request, recipe_id: int, body: RecipeUpdate):
    """Update a recipe. If ingredients are updated, nutrient totals are recomputed."""
    recipe_repo = _recipe_repo(request)
    recipe = recipe_repo.get(recipe_id)
    if not recipe or recipe["user_id"] != current_user_id(request):
        raise HTTPException(404, "Recipe not found")

    updates = body.model_dump(exclude_unset=True)
    if "ingredients" in updates:
        food_repo = _food_repo(request)
        resolved = _resolve_ingredients(
            food_repo, body.ingredients, current_user_id(request)
        )
        total_weight = updates.get("total_weight_g", recipe["total_weight_g"])
        servings = updates.get("servings", recipe["servings"])
        per_100, per_serving = compute_recipe_nutrients(resolved, total_weight, servings)
        updates["ingredients"] = resolved
        updates["nutrients_per_100"] = per_100
        updates["nutrients_per_serving"] = per_serving

    recipe_repo.update(recipe_id, **updates)
    return recipe_repo.get(recipe_id)


@router.delete("/{recipe_id}", status_code=204, summary="Delete recipe")
def delete_recipe(request: Request, recipe_id: int):
    """Delete a recipe."""
    recipe = _recipe_repo(request).get(recipe_id)
    if not recipe or recipe["user_id"] != current_user_id(request):
        raise HTTPException(404, "Recipe not found")
    if not _recipe_repo(request).delete(recipe_id):
        raise HTTPException(404, "Recipe not found")
