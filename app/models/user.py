from datetime import datetime

from pydantic import BaseModel, Field


class UserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class User(BaseModel):
    id: int
    name: str
    created_at: datetime
    updated_at: datetime


class UserWithToken(User):
    token: str
