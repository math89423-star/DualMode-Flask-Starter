from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class ItemCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = ""


class ItemResponse(BaseModel):
    id: int
    title: str
    description: Optional[str]
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class ErrorResponse(BaseModel):
    error: str
    details: Optional[list] = None
