from fastapi import APIRouter, HTTPException, Request

from app.auth import current_user_id
from app.models.activity import DailyActivity
from app.repositories.activity import ActivityRepository

router = APIRouter(prefix="/activity", tags=["activity"])


@router.get("/daily/{date}", response_model=DailyActivity, summary="Get daily activity summary")
def get_daily_activity(request: Request, date: str):
    """Get the normalized daily step total for a given date (YYYY-MM-DD)."""
    repo = ActivityRepository(request.app.state.db)
    row = repo.get_daily(user_id=current_user_id(request), date=date)
    if not row:
        raise HTTPException(status_code=404, detail="No activity data for this date")
    return row


@router.get("/range", response_model=list[DailyActivity], summary="Get daily activity over a date range")
def get_activity_range(request: Request, start: str, end: str):
    """Get daily activity records for a date range (YYYY-MM-DD). Returns only days with data."""
    repo = ActivityRepository(request.app.state.db)
    return repo.list_by_date_range(user_id=current_user_id(request), start=start, end=end)
