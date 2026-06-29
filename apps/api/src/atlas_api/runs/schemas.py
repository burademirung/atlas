from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RunCreateIn(BaseModel):
    question: str = Field(min_length=3, max_length=500)


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    question: str
    status: str
    created_at: datetime


class SourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    url: str
    title: str | None = None
    snippet: str | None = None


class RunDetailOut(RunOut):
    report: str | None = None
    sources: list[SourceOut] = []
