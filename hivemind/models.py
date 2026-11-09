from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

Category = Literal["coffee", "general", "help", "accessibility", "demo"]
ExpiryChoice = Literal[
    "15m", "30m", "45m", "1h", "75m", "90m", "105m", "120m", "end_of_day", "custom"
]


class ReportInput(BaseModel):
    content: str = Field(min_length=1, max_length=500)
    location: str | None = Field(default=None, max_length=120)
    category: Category = "general"
    expiration: ExpiryChoice = "1h"
    starts_at: datetime | None = None
    custom_expires_at: datetime | None = None

    @field_validator("content")
    @classmethod
    def non_blank_content(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("report cannot be blank")
        return value

    @field_validator("location")
    @classmethod
    def normalize_location(cls, value: str | None) -> str | None:
        return value.strip() if value and value.strip() else None


class OpportunitySummaryInput(BaseModel):
    window_minutes: Literal[30, 60, 90, 120] = 30
