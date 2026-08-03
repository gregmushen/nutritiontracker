from fastapi import APIRouter, HTTPException, Request

from app.auth import current_user_id
from app.models.weight import WeightEntry, WeightEntryCreate, WeightEntryUpdate
from app.repositories.weight import WeightRepository

router = APIRouter(prefix="/weight", tags=["weight"])


def _repo(request: Request) -> WeightRepository:
    return WeightRepository(request.app.state.db)


@router.post("", status_code=201, response_model=WeightEntry, summary="Log body weight")
def create_weight(request: Request, body: WeightEntryCreate):
    """Log a body weight measurement for a date."""
    repo = _repo(request)
    wid = repo.create(
        user_id=current_user_id(request),
        date=body.date, weight_kg=body.weight_kg, notes=body.notes,
    )
    return repo.get(wid)


@router.get("", response_model=list[WeightEntry], summary="Get weight entries")
def list_weight(
    request: Request, date: str | None = None,
    start: str | None = None, end: str | None = None,
):
    """Get weight entries by date (?date=YYYY-MM-DD) or date range (?start=&end=)."""
    repo = _repo(request)
    if date:
        return repo.list_by_date_range(
            user_id=current_user_id(request), start=date, end=date
        )
    if start and end:
        return repo.list_by_date_range(
            user_id=current_user_id(request), start=start, end=end
        )
    raise HTTPException(400, "Provide date or start+end parameters")


@router.patch("/{entry_id}", response_model=WeightEntry, summary="Update weight entry")
def update_weight(request: Request, entry_id: int, body: WeightEntryUpdate):
    """Update a weight entry."""
    repo = _repo(request)
    entry = repo.get(entry_id)
    if not entry or entry["user_id"] != current_user_id(request):
        raise HTTPException(404, "Weight entry not found")
    updates = body.model_dump(exclude_unset=True)
    repo.update(entry_id, **updates)
    return repo.get(entry_id)


@router.delete("/{entry_id}", status_code=204, summary="Delete weight entry")
def delete_weight(request: Request, entry_id: int):
    """Delete a weight entry."""
    repo = _repo(request)
    entry = repo.get(entry_id)
    if not entry or entry["user_id"] != current_user_id(request):
        raise HTTPException(404, "Weight entry not found")
    if not repo.delete(entry_id):
        raise HTTPException(404, "Weight entry not found")
