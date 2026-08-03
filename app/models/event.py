from typing import Annotated, Optional

from pydantic import AfterValidator, BaseModel, Field, field_validator


def _require_content(value: str, field: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{field} must not be blank")
    return stripped


def _validate_time_of_day(value: str) -> str:
    """Accept HH:MM or HH:MM:SS, local wall-clock, matching `date`.

    Left as a plain local time rather than a timestamp: attaching a UTC offset
    to something the user reported as "3pm" is how entries end up filed under
    the wrong day.
    """
    from datetime import time as time_cls

    try:
        return time_cls.fromisoformat(value).isoformat()
    except ValueError:
        raise ValueError("at must be a local time, HH:MM or HH:MM:SS") from None


def _validate_iso_date(value: str) -> str:
    from datetime import date as date_cls

    try:
        parsed = date_cls.fromisoformat(value)
    except ValueError:
        raise ValueError("date must be YYYY-MM-DD") from None
    if parsed.isoformat() != value:
        raise ValueError("date must be YYYY-MM-DD")
    return value


CanonicalDate = Annotated[str, AfterValidator(_validate_iso_date)]


class EventTypeCreate(BaseModel):
    name: str = Field(max_length=200)
    unit: Optional[str] = Field(default=None, max_length=50)
    notes: Optional[str] = None

    @field_validator("name")
    @classmethod
    def _name_has_content(cls, value: str) -> str:
        return _require_content(value, "name")

    @field_validator("unit")
    @classmethod
    def _unit_is_absent_or_meaningful(cls, value: Optional[str]) -> Optional[str]:
        # A whitespace-only unit reads as "unitless" but stores as a value that
        # is not None, which would defeat every "was a unit given?" check.
        if value is None:
            return None
        return _require_content(value, "unit")


class EventTypeUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=200)
    unit: Optional[str] = Field(default=None, max_length=50)
    notes: Optional[str] = None

    @field_validator("name")
    @classmethod
    def _name_has_content(cls, value: Optional[str]) -> str:
        if value is None:
            raise ValueError("name cannot be null")
        return _require_content(value, "name")


class EventType(BaseModel):
    id: int
    user_id: int
    name: str
    unit: Optional[str]
    notes: Optional[str]
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class EventCreate(BaseModel):
    event_type_id: int
    date: CanonicalDate
    at: Optional[str] = None
    value: Optional[float] = None
    unit: Optional[str] = Field(default=None, max_length=50)
    notes: Optional[str] = None

    @field_validator("at")
    @classmethod
    def _at_is_a_local_time(cls, value: Optional[str]) -> Optional[str]:
        return None if value is None else _validate_time_of_day(value)


class EventUpdate(BaseModel):
    date: Optional[CanonicalDate] = None
    at: Optional[str] = None
    value: Optional[float] = None
    unit: Optional[str] = Field(default=None, max_length=50)
    notes: Optional[str] = None

    @field_validator("date")
    @classmethod
    def _date_cannot_be_null(cls, value: Optional[str]) -> str:
        if value is None:
            raise ValueError("date cannot be null")
        return value

    @field_validator("at")
    @classmethod
    def _at_is_a_local_time(cls, value: Optional[str]) -> Optional[str]:
        return None if value is None else _validate_time_of_day(value)


class Event(BaseModel):
    id: int
    user_id: int
    event_type_id: int
    event_type_name: str
    date: str
    at: Optional[str]
    value: Optional[float]
    unit: Optional[str]
    notes: Optional[str]
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class EventSummaryRow(BaseModel):
    event_type_id: int
    event_type_name: str
    unit: Optional[str]
    count: int
    unmeasured_count: int
    total_value: Optional[float]

    model_config = {"from_attributes": True}
