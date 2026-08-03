from fastapi import APIRouter, HTTPException, Query, Request

from app.auth import current_user_id
from app.models.food import (
    NUTRIENT_FIELDS,
    FoodCreate,
    FoodOut,
    FoodSourceOut,
    FoodUpdate,
)
from app.providers.open_food_facts import fetch_off_by_barcode
from app.repositories.foods import FoodRepository
from app.services.food_search import (
    MAX_SEARCH_LIMIT,
    MAX_SEARCH_OFFSET,
    FoodSearchService,
)

router = APIRouter(prefix="/foods", tags=["foods"])

OFF_REFRESH_FIELDS = (
    "brand",
    "image_url",
    "serving_quantity",
    "serving_unit",
    "serving_size_text",
    "ingredients_text",
    "allergens_tags",
    "dietary_tags",
    "categories_tags",
    "labels_tags",
    "countries_tags",
    "nutriscore_grade",
    "nova_group",
    "product_quantity",
    "product_quantity_unit",
)


def _repo(request: Request) -> FoodRepository:
    return FoodRepository(request.app.state.db)


def _search_svc(request: Request) -> FoodSearchService:
    return FoodSearchService(_repo(request))


@router.get("/search", response_model=list[FoodOut], summary="Search foods")
def search_foods(
    request: Request,
    q: str,
    source: str = "all",
    limit: int = Query(default=20, ge=1, le=MAX_SEARCH_LIMIT),
    offset: int = Query(default=0, ge=0, le=MAX_SEARCH_OFFSET),
):
    """Search the food database by name or brand. Supports prefix matching ('chick' matches 'chicken breast').

    Results are ordered by text relevance adjusted by source quality, so a generic
    query returns measured composition data ahead of transcribed nutrition labels
    while a branded query still finds the brand. Duplicates of the same food across
    sources are collapsed, preferring the higher-quality source (see
    `GET /foods/sources` for tiers) and then the more complete nutrient profile.

    Filter by source with any code from `GET /foods/sources`, or `all`, `usda` for
    every USDA dataset, or `cronometer` for everything imported from a personal
    Cronometer export.
    A nutrient of `null` means the source does not report it; `0` means it was measured as zero."""
    return _search_svc(request).search(
        q, source=source, user_id=current_user_id(request), limit=limit, offset=offset
    )


@router.get(
    "/sources", response_model=list[FoodSourceOut], summary="List food data sources"
)
def list_sources(request: Request):
    """List the food composition datasets backing the catalog.

    Each entry gives the publisher, licence, required citation text and the quality
    `tier` used to rank duplicate foods during search (lower is better), plus how many
    foods currently come from that source.
    """
    return _repo(request).list_sources()


def _has_nutrients(food: dict) -> bool:
    return any(food.get(field) is not None for field in NUTRIENT_FIELDS)


@router.get("/barcode/{barcode}", response_model=FoodOut, summary="Look up food by barcode")
def get_by_barcode(request: Request, barcode: str):
    """Look up a food by EAN or UPC barcode.

    On a local miss, fetches and caches a matching live OpenFoodFacts record.
    If a local OpenFoodFacts record has no nutrient data, refreshes it from
    the live API. If that also has no data, returns the local record as-is so
    the caller can PATCH it with correct values.
    """
    repo = _repo(request)
    user_id = current_user_id(request)
    food = repo.get_by_barcode(barcode, user_id=user_id)
    if not food:
        fresh = fetch_off_by_barcode(barcode)
        if not fresh:
            raise HTTPException(404, "Food not found")
        food_id = repo.create(**fresh)
        return repo.get(food_id, user_id=user_id)

    if not _has_nutrients(food) and food.get("source") == "open_food_facts":
        fresh = fetch_off_by_barcode(barcode)
        if fresh:
            # `is not None`, not truthiness: a label declaring 0 g is a
            # measured zero and has to overwrite the stored NULL.
            updates = {
                key: fresh[key]
                for key in (*NUTRIENT_FIELDS, *OFF_REFRESH_FIELDS)
                if key in fresh and fresh[key] is not None
            }
            if updates:
                repo.update(food["id"], **updates)
                food = repo.get(food["id"], user_id=user_id)

    return food


@router.get("/{food_id}", response_model=FoodOut, summary="Get food by ID")
def get_food(request: Request, food_id: int):
    """Retrieve a single food record by its ID."""
    food = _repo(request).get(food_id, user_id=current_user_id(request))
    if not food:
        raise HTTPException(404, "Food not found")
    return food


@router.post("", status_code=201, response_model=FoodOut, summary="Create custom food")
def create_food(request: Request, body: FoodCreate):
    """Create a custom food entry. Provide name, source='custom', and nutrient values per 100g."""
    repo = _repo(request)
    nutrients = body.nutrients.model_dump()
    data = body.model_dump(exclude={"nutrients"})
    data.update(nutrients)
    food_id = repo.create(**data, owner_user_id=current_user_id(request))
    return repo.get(food_id, user_id=current_user_id(request))


@router.patch("/{food_id}", response_model=FoodOut, summary="Update custom food")
def update_food(request: Request, food_id: int, body: FoodUpdate):
    """Update fields on a custom food record."""
    repo = _repo(request)
    food = repo.get(food_id, user_id=current_user_id(request))
    if not food or food["owner_user_id"] != current_user_id(request):
        raise HTTPException(404, "Food not found")
    updates = body.model_dump(exclude_unset=True)
    if "nutrients" in updates and updates["nutrients"] is not None:
        nutrients = updates.pop("nutrients")
        updates.update(nutrients)
    elif "nutrients" in updates:
        updates.pop("nutrients")
    repo.update(food_id, **updates)
    return repo.get(food_id, user_id=current_user_id(request))


@router.delete("/{food_id}", status_code=204, summary="Delete custom food")
def delete_food(request: Request, food_id: int):
    """Delete a custom food record. Only custom foods can be deleted."""
    repo = _repo(request)
    food = repo.get(food_id, user_id=current_user_id(request))
    if not food or food["owner_user_id"] != current_user_id(request):
        raise HTTPException(404, "Food not found")
    if not repo.delete(food_id):
        raise HTTPException(404, "Food not found")
