from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RunCreateIn(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    # Leaked data categories (e.g. ["ssn", "financial"]); each maps to a curated
    # breach playbook injected into the agent's writer node. Defaults to empty so
    # the field is fully backward-compatible with existing clients.
    data_types: list[str] = Field(default_factory=list, max_length=16)


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
