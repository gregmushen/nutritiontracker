import sqlite3
from math import isfinite

from fastapi import APIRouter, HTTPException, Query, Request

from app.auth import current_user_id
from app.models.event import (
    CanonicalDate,
    Event,
    EventCreate,
    EventSummaryRow,
    EventType,
    EventTypeCreate,
    EventTypeUpdate,
    EventUpdate,
)
from app.repositories.events import EventRepository, EventTypeRepository

router = APIRouter(prefix="/events", tags=["events"])


def _types(request: Request) -> EventTypeRepository:
    return EventTypeRepository(request.app.state.db)


def _events(request: Request) -> EventRepository:
    return EventRepository(request.app.state.db)


def _reject_non_finite_value(value: float | None) -> None:
    if value is not None and not isfinite(value):
        raise HTTPException(status_code=422, detail="Event value must be finite")


# Literal segments are declared before /{event_id} so that "types" and
# "summary" are not parsed as an event id.


@router.post("/types", response_model=EventType, status_code=201,
             summary="Define an event type")
def create_event_type(request: Request, body: EventTypeCreate):
    """Define a category of event to log against.

    Nothing is pre-seeded: an event type is whatever you decide to track, and
    its unit is whatever you measure it in.
    """
    user_id = current_user_id(request)
    repo = _types(request)
    try:
        type_id = repo.create(
            user_id=user_id, name=body.name, unit=body.unit, notes=body.notes
        )
    except sqlite3.IntegrityError:
        raise HTTPException(
            status_code=409, detail=f"Event type '{body.name}' already exists"
        ) from None
    return repo.get(type_id, user_id=user_id)


@router.get("/types", response_model=list[EventType], summary="List event types")
def list_event_types(request: Request):
    """List every event type you have defined."""
    return _types(request).list(user_id=current_user_id(request))


@router.get("/types/{type_id}", response_model=EventType, summary="Get an event type")
def get_event_type(request: Request, type_id: int):
    """Get a single event type."""
    user_id = current_user_id(request)
    event_type = _types(request).get(type_id, user_id=user_id)
    if event_type is None:
        raise HTTPException(status_code=404, detail="Event type not found")
    return event_type


@router.patch("/types/{type_id}", response_model=EventType,
              summary="Update an event type")
def update_event_type(request: Request, type_id: int, body: EventTypeUpdate):
    """Partially update an event type.

    Changing the unit does not rewrite events already logged: each event keeps
    the unit it was recorded with, so past readings keep their meaning.
    """
    user_id = current_user_id(request)
    repo = _types(request)
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    if repo.get(type_id, user_id=user_id) is None:
        raise HTTPException(status_code=404, detail="Event type not found")
    try:
        repo.update(type_id, user_id=user_id, **updates)
    except sqlite3.IntegrityError:
        raise HTTPException(
            status_code=409, detail=f"Event type '{updates.get('name')}' already exists"
        ) from None
    return repo.get(type_id, user_id=user_id)


@router.delete("/types/{type_id}", status_code=204, summary="Delete an event type")
def delete_event_type(
    request: Request,
    type_id: int,
    cascade: bool = Query(
        default=False,
        description="Also delete every event logged against this type.",
    ),
):
    """Delete an event type.

    Refuses while events still reference it, since deleting the type would
    otherwise take logged history with it silently. Pass `cascade=true` to
    delete the events too.
    """
    user_id = current_user_id(request)
    repo = _types(request)
    if repo.get(type_id, user_id=user_id) is None:
        raise HTTPException(status_code=404, detail="Event type not found")
    logged = repo.count_events(type_id, user_id=user_id)
    if logged and not cascade:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Event type still has {logged} event(s). "
                "Delete them first, or pass cascade=true to remove them with it."
            ),
        )
    repo.delete(type_id, user_id=user_id, cascade=cascade)


@router.get("/summary", response_model=list[EventSummaryRow],
            summary="Summarize events by type")
def summarize_events(
    request: Request,
    start: CanonicalDate | None = Query(
        default=None, description="Earliest date, YYYY-MM-DD"
    ),
    end: CanonicalDate | None = Query(
        default=None, description="Latest date, YYYY-MM-DD"
    ),
):
    """Count and total events per type over a date range.

    Rows are grouped by unit as well as type, so a type whose unit changed
    part-way through reports each unit separately instead of adding values
    that do not share a scale. `total_value` is null when nothing in the group
    carried a value, and `unmeasured_count` says how many were logged without
    one.
    """
    return _events(request).summary(
        user_id=current_user_id(request), start=start, end=end
    )


@router.post("", response_model=Event, status_code=201, summary="Log an event")
def create_event(request: Request, body: EventCreate):
    """Log an event against one of your event types.

    `value` is optional and `0` is a real measurement, not a missing one. When
    `unit` is omitted the event type's unit is copied onto the event, so the
    reading stays interpretable if the type is edited later.
    """
    user_id = current_user_id(request)
    _reject_non_finite_value(body.value)
    event_type = _types(request).get(body.event_type_id, user_id=user_id)
    if event_type is None:
        raise HTTPException(status_code=404, detail="Event type not found")

    fields = body.model_dump(exclude_unset=True)
    unit = body.unit if "unit" in fields else event_type["unit"]

    repo = _events(request)
    event_id = repo.create(
        user_id=user_id,
        event_type_id=body.event_type_id,
        date=body.date,
        at=body.at,
        value=body.value,
        unit=unit,
        notes=body.notes,
    )
    return repo.get(event_id, user_id=user_id)


@router.get("", response_model=list[Event], summary="List events")
def list_events(
    request: Request,
    start: CanonicalDate | None = Query(
        default=None, description="Earliest date, YYYY-MM-DD"
    ),
    end: CanonicalDate | None = Query(
        default=None, description="Latest date, YYYY-MM-DD"
    ),
    event_type_id: int | None = Query(default=None, description="Filter by type"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    """List events, most recent first, optionally filtered by date and type."""
    return _events(request).list(
        user_id=current_user_id(request),
        start=start,
        end=end,
        event_type_id=event_type_id,
        limit=limit,
        offset=offset,
    )


@router.get("/{event_id}", response_model=Event, summary="Get an event")
def get_event(request: Request, event_id: int):
    """Get a single logged event."""
    event = _events(request).get(event_id, user_id=current_user_id(request))
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@router.patch("/{event_id}", response_model=Event, summary="Update an event")
def update_event(request: Request, event_id: int, body: EventUpdate):
    """Partially update a logged event."""
    user_id = current_user_id(request)
    repo = _events(request)
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    if "value" in updates:
        _reject_non_finite_value(updates["value"])
    if repo.get(event_id, user_id=user_id) is None:
        raise HTTPException(status_code=404, detail="Event not found")
    repo.update(event_id, user_id=user_id, **updates)
    return repo.get(event_id, user_id=user_id)


@router.delete("/{event_id}", status_code=204, summary="Delete an event")
def delete_event(request: Request, event_id: int):
    """Delete a logged event."""
    user_id = current_user_id(request)
    repo = _events(request)
    if repo.get(event_id, user_id=user_id) is None:
        raise HTTPException(status_code=404, detail="Event not found")
    repo.delete(event_id, user_id=user_id)
