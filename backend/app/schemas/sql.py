"""Pydantic schemas for NL-to-SQL requests and responses."""

from typing import Any

from pydantic import BaseModel, Field


class SQLGenerateRequest(BaseModel):
    question: str = Field(min_length=1)
    model: str | None = None


class SQLGenerateResponse(BaseModel):
    sql: str


class SQLAskRequest(BaseModel):
    question: str = Field(min_length=1)
    model: str | None = None
    limit: int = Field(default=50, ge=1, le=500)


class SQLAskResponse(BaseModel):
    sql: str
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
