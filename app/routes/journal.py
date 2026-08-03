from fastapi import APIRouter, HTTPException, Request

from app.auth import current_user_id
from app.models.journal import JournalEntry, JournalEntryCreate, JournalEntryUpdate
from app.repositories.journal import JournalRepository

router = APIRouter(prefix="/journal", tags=["journal"])


@router.post("", response_model=JournalEntry, status_code=201, summary="Create journal entry")
def create_journal_entry(request: Request, body: JournalEntryCreate):
    """Create a daily journal entry with optional mood, stress, and sleep scores."""
    repo = JournalRepository(request.app.state.db)
    entry_id = repo.create(
        user_id=current_user_id(request),
        date=body.date,
        body=body.body,
        tags=body.tags,
        mood_score=body.mood_score,
        stress_score=body.stress_score,
        sleep_quality=body.sleep_quality,
    )
    return repo.get(entry_id)


@router.get("", response_model=list[JournalEntry], summary="Get journal entries over a date range")
def get_journal_range(request: Request, start: str, end: str):
    """Get all journal entries for a date range (YYYY-MM-DD)."""
    repo = JournalRepository(request.app.state.db)
    return repo.list_by_date_range(user_id=current_user_id(request), start=start, end=end)


@router.get("/{date}", response_model=list[JournalEntry], summary="Get journal entries for a date")
def get_journal_by_date(request: Request, date: str):
    """Get all journal entries for a given date (YYYY-MM-DD)."""
    repo = JournalRepository(request.app.state.db)
    return repo.list_by_date(user_id=current_user_id(request), date=date)


@router.patch("/{entry_id}", response_model=JournalEntry, summary="Update a journal entry")
def update_journal_entry(request: Request, entry_id: int, body: JournalEntryUpdate):
    """Partially update a journal entry."""
    repo = JournalRepository(request.app.state.db)
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    entry = repo.get(entry_id)
    if entry is None or entry["user_id"] != current_user_id(request):
        raise HTTPException(status_code=404, detail="Journal entry not found")
    repo.update(entry_id, **updates)
    return repo.get(entry_id)


@router.delete("/{entry_id}", status_code=204, summary="Delete a journal entry")
def delete_journal_entry(request: Request, entry_id: int):
    """Delete a journal entry."""
    repo = JournalRepository(request.app.state.db)
    entry = repo.get(entry_id)
    if entry is None or entry["user_id"] != current_user_id(request):
        raise HTTPException(status_code=404, detail="Journal entry not found")
    if not repo.delete(entry_id):
        raise HTTPException(status_code=404, detail="Journal entry not found")
