"""Schemas for live-data chat endpoint."""

from typing import Any

from pydantic import BaseModel, Field


class LiveChatRequest(BaseModel):
    query: str = Field(min_length=1)
    model: str | None = None


class LiveChatResponse(BaseModel):
    mode: str
    query: str
    model: str
    live_data: dict[str, Any]
    answer: str
    fallback_used: bool
