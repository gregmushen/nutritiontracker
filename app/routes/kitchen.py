from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.auth import current_user_id
from app.models.kitchen import (
    FavoriteMeal,
    FavoriteMealCreate,
    InventoryItem,
    InventoryItemCreate,
    MealMatch,
    MealMatchRequest,
    ShoppingListItem,
    ShoppingListItemCreate,
)
from app.repositories.kitchen import KitchenRepository
from app.services.kitchen import (
    canonicalize_ingredient_name,
    generate_shopping_items_for_meals,
    rank_favorite_meals,
)

router = APIRouter(prefix="/kitchen", tags=["kitchen"])


class ShoppingGenerateRequest(BaseModel):
    meal_ids: list[int]


class ShoppingItemPatch(BaseModel):
    checked: bool


def _repo(request: Request) -> KitchenRepository:
    return KitchenRepository(request.app.state.db)


def _ingredient_payload(item) -> dict:
    canonical = canonicalize_ingredient_name(item.name)
    return {
        "display_name": item.name.strip(),
        "canonical_name": canonical,
        "role": item.role,
        "category": item.category,
    }


@router.post(
    "/inventory",
    status_code=201,
    response_model=InventoryItem,
    summary="Create or update kitchen inventory item",
)
def upsert_inventory_item(request: Request, body: InventoryItemCreate):
    canonical = canonicalize_ingredient_name(body.name)
    return _repo(request).upsert_inventory_item(
        user_id=current_user_id(request),
        display_name=body.name.strip(),
        canonical_name=canonical,
        status=body.status,
        location=body.location,
        category=body.category,
        notes=body.notes,
    )


@router.get(
    "/inventory", response_model=list[InventoryItem], summary="List kitchen inventory"
)
def list_inventory(
    request: Request,
    status: str | None = None,
    location: str | None = None,
    category: str | None = None,
    q: str | None = None,
):
    return _repo(request).list_inventory(
        user_id=current_user_id(request),
        status=status,
        location=location,
        category=category,
        query=q,
    )


@router.delete(
    "/inventory/{item_id}", status_code=204, summary="Delete kitchen inventory item"
)
def delete_inventory_item(request: Request, item_id: int):
    if not _repo(request).delete_inventory_item(
        user_id=current_user_id(request), item_id=item_id
    ):
        raise HTTPException(404, "Inventory item not found")


@router.post(
    "/meals", status_code=201, response_model=FavoriteMeal, summary="Create favorite meal"
)
def create_favorite_meal(request: Request, body: FavoriteMealCreate):
    ingredients = [_ingredient_payload(item) for item in body.ingredients]
    return _repo(request).create_favorite_meal(
        user_id=current_user_id(request),
        name=body.name,
        tags=body.tags,
        prep_time_minutes=body.prep_time_minutes,
        effort=body.effort,
        favorite_score=body.favorite_score,
        nutrition_template_id=body.nutrition_template_id,
        ingredients=ingredients,
    )


@router.get("/meals", response_model=list[FavoriteMeal], summary="List favorite meals")
def list_favorite_meals(request: Request):
    return _repo(request).list_favorite_meals(user_id=current_user_id(request))


@router.post(
    "/meals/{meal_id}/made",
    response_model=FavoriteMeal,
    summary="Mark favorite meal made",
)
def mark_meal_made(request: Request, meal_id: int):
    made_at = datetime.now(UTC).isoformat()
    meal = _repo(request).mark_meal_made(
        user_id=current_user_id(request),
        meal_id=meal_id,
        made_at=made_at,
    )
    if not meal:
        raise HTTPException(404, "Favorite meal not found")
    return meal


@router.post(
    "/matches",
    response_model=list[MealMatch],
    summary="Rank meals from current kitchen memory",
)
def rank_meals(request: Request, body: MealMatchRequest):
    repo = _repo(request)
    meals = repo.list_favorite_meals(user_id=current_user_id(request))
    inventory = repo.list_inventory(user_id=current_user_id(request))
    return rank_favorite_meals(
        meals=meals,
        inventory=inventory,
        request_filters=body.model_dump(exclude_none=True),
    )


@router.post(
    "/shopping-list",
    status_code=201,
    response_model=ShoppingListItem,
    summary="Add shopping list item",
)
def add_shopping_item(request: Request, body: ShoppingListItemCreate):
    canonical = canonicalize_ingredient_name(body.name)
    return _repo(request).upsert_shopping_list_item(
        user_id=current_user_id(request),
        display_name=body.name.strip(),
        canonical_name=canonical,
        source=body.source,
        linked_meal_ids=body.linked_meal_ids,
        notes=body.notes,
    )


@router.get(
    "/shopping-list",
    response_model=list[ShoppingListItem],
    summary="List shopping list items",
)
def list_shopping_items(request: Request, checked: bool | None = None):
    return _repo(request).list_shopping_items(
        user_id=current_user_id(request),
        checked=checked,
    )


@router.post(
    "/shopping-list/generate",
    response_model=list[ShoppingListItem],
    summary="Generate shopping list items from selected meals",
)
def generate_shopping_list(request: Request, body: ShoppingGenerateRequest):
    repo = _repo(request)
    meals = []
    for meal_id in body.meal_ids:
        meal = repo.get_favorite_meal(
            user_id=current_user_id(request), meal_id=meal_id
        )
        if not meal:
            raise HTTPException(404, f"Favorite meal {meal_id} not found")
        meals.append(meal)

    inventory = repo.list_inventory(user_id=current_user_id(request))
    generated = generate_shopping_items_for_meals(meals=meals, inventory=inventory)
    return [
        repo.upsert_shopping_list_item(
            user_id=current_user_id(request),
            display_name=item["display_name"],
            canonical_name=item["canonical_name"],
            source=item["source"],
            linked_meal_ids=item["linked_meal_ids"],
        )
        for item in generated
    ]


@router.patch(
    "/shopping-list/{item_id}",
    response_model=ShoppingListItem,
    summary="Check or uncheck shopping list item",
)
def patch_shopping_item(request: Request, item_id: int, body: ShoppingItemPatch):
    item = _repo(request).set_shopping_item_checked(
        user_id=current_user_id(request),
        item_id=item_id,
        checked=body.checked,
    )
    if not item:
        raise HTTPException(404, "Shopping list item not found")
    return item
