import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DatasetResponse(BaseModel):
    id: uuid.UUID
    name: str
    sha256: str
    source_url: str
    row_count: int
    column_count: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class ReportTitle(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    model_config = ConfigDict(extra="forbid")

    @field_validator("title")
    @classmethod
    def nonblank_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Title cannot be blank")
        return value


class ReportCreate(ReportTitle):
    dataset_id: uuid.UUID


class ReportResponse(BaseModel):
    id: uuid.UUID
    dataset_id: uuid.UUID
    title: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)
