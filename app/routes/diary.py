from fastapi import APIRouter, HTTPException, Request

from app.auth import current_user_id
from app.models.diary import DiaryEntry, DiaryEntryCreate, DiaryEntryUpdate
from app.repositories.diary import DiaryRepository
from app.repositories.foods import FoodRepository
from app.services.diary import build_food_snapshot, compute_entry_nutrients
from app.services.unit_conversion import convert_to_grams

router = APIRouter(tags=["diary"])


def _diary_repo(request: Request) -> DiaryRepository:
    return DiaryRepository(request.app.state.db)


def _food_repo(request: Request) -> FoodRepository:
    return FoodRepository(request.app.state.db)


@router.get("/diary/search", response_model=list[DiaryEntry], summary="Search diary entries by food name")
def search_entries(request: Request, q: str):
    """Search all diary entries where the food name contains the query string (case-insensitive). Returns results newest first."""
    return _diary_repo(request).search_by_food_name(
        user_id=current_user_id(request), query=q
    )


@router.get("/diary/{date}", response_model=list[DiaryEntry], summary="List diary entries for a date")
def list_entries(request: Request, date: str):
    """Get all diary entries for the given date (YYYY-MM-DD format)."""
    return _diary_repo(request).list_by_date(
        user_id=current_user_id(request), date=date
    )


@router.post("/diary/{date}/entries", status_code=201, response_model=DiaryEntry, summary="Log a food diary entry")
def create_entry(request: Request, date: str, body: DiaryEntryCreate):
    """Log a food to the diary. Automatically converts the amount to grams, computes nutrient totals, and snapshots the food record."""
    food_repo = _food_repo(request)
    user_id = current_user_id(request)
    food = food_repo.get(body.food_id, user_id=user_id)
    if not food:
        raise HTTPException(404, "Food not found")

    conversion = convert_to_grams(
        body.amount, body.unit,
        density_g_per_ml=food.get("density_g_per_ml"),
        serving_quantity=food.get("serving_quantity"),
        serving_unit=food.get("serving_unit"),
    )
    nutrients = compute_entry_nutrients(food, conversion.grams)
    snapshot = build_food_snapshot(food)

    diary_repo = _diary_repo(request)
    entry_id = diary_repo.create(
        user_id=user_id, date=date,
        meal_type=body.meal_type, food_id=body.food_id,
        food_snapshot=snapshot, food_name=snapshot.get("name", ""),
        amount=body.amount, unit=body.unit, grams=conversion.grams,
        nutrients_total=nutrients,
    )
    return diary_repo.get(entry_id)


@router.patch("/diary/entries/{entry_id}", response_model=DiaryEntry, summary="Update a diary entry")
def update_entry(request: Request, entry_id: int, body: DiaryEntryUpdate):
    """Update the amount, unit, or meal type of a diary entry. Nutrient totals are recomputed if amount or unit changes."""
    diary_repo = _diary_repo(request)
    entry = diary_repo.get(entry_id)
    if not entry or entry["user_id"] != current_user_id(request):
        raise HTTPException(404, "Entry not found")

    updates = body.model_dump(exclude_unset=True)
    if "amount" in updates or "unit" in updates:
        food = entry["food_snapshot"]
        amount = updates.get("amount", entry["amount"])
        unit = updates.get("unit", entry["unit"])
        conversion = convert_to_grams(
            amount, unit,
            density_g_per_ml=food.get("density_g_per_ml"),
            serving_quantity=food.get("serving_quantity"),
            serving_unit=food.get("serving_unit"),
        )
        updates["grams"] = conversion.grams
        updates["nutrients_total"] = compute_entry_nutrients(food, conversion.grams)

    diary_repo.update(entry_id, **updates)
    return diary_repo.get(entry_id)


@router.delete("/diary/entries/{entry_id}", status_code=204, summary="Delete a diary entry")
def delete_entry(request: Request, entry_id: int):
    """Delete a diary entry by ID."""
    diary_repo = _diary_repo(request)
    entry = diary_repo.get(entry_id)
    if not entry or entry["user_id"] != current_user_id(request):
        raise HTTPException(404, "Entry not found")
    if not diary_repo.delete(entry_id):
        raise HTTPException(404, "Entry not found")
