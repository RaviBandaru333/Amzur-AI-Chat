"""Response formatting — structure and enhance responses for consistency.

Wraps various response types (text, table, chart, etc.) with metadata
and improves readability without modifying existing service outputs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
from typing import Any


class ResponseType(str, Enum):
    """Response content type."""

    TEXT = "text"
    TABLE = "table"
    CHART = "chart"
    JSON = "json"
    IMAGE = "image"
    HYBRID = "hybrid"  # Multiple response types


@dataclass
class ResponseMetadata:
    """Metadata attached to responses."""

    source: str  # Source of data (e.g., "api:weather", "db:users", "file:sales.xlsx")
    timestamp: str  # ISO format timestamp
    intent: str | None = None
    tool_used: str | None = None
    execution_time_ms: float | None = None
    cached: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class StructuredResponse:
    """Structured response container."""

    type: ResponseType
    content: Any  # Response content (varies by type)
    summary: str | None = None  # Human-readable summary
    metadata: ResponseMetadata | None = None
    follow_ups: list[str] | None = None  # Suggested follow-up questions

    def to_dict(self) -> dict:
        """Convert to dict for JSON serialization."""
        return {
            "type": self.type.value,
            "content": self.content,
            "summary": self.summary,
            "metadata": self.metadata.to_dict() if self.metadata else None,
            "follow_ups": self.follow_ups or [],
        }

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), ensure_ascii=False, default=str)

    @classmethod
    def text(
        cls,
        content: str,
        source: str = "llm",
        summary: str | None = None,
        follow_ups: list[str] | None = None,
    ) -> StructuredResponse:
        """Create a text response."""
        return cls(
            type=ResponseType.TEXT,
            content=content,
            summary=summary or content[:200],
            metadata=ResponseMetadata(source=source, timestamp=datetime.utcnow().isoformat()),
            follow_ups=follow_ups,
        )

    @classmethod
    def table(
        cls,
        columns: list[str],
        rows: list[dict],
        source: str = "database",
        title: str | None = None,
        summary: str | None = None,
    ) -> StructuredResponse:
        """Create a table response."""
        return cls(
            type=ResponseType.TABLE,
            content={
                "columns": columns,
                "rows": rows,
                "title": title,
                "row_count": len(rows),
            },
            summary=summary or f"Retrieved {len(rows)} rows from {source}",
            metadata=ResponseMetadata(source=source, timestamp=datetime.utcnow().isoformat()),
        )

    @classmethod
    def chart(
        cls,
        chart_type: str,
        data: dict,
        source: str = "database",
        title: str | None = None,
        summary: str | None = None,
    ) -> StructuredResponse:
        """Create a chart response."""
        return cls(
            type=ResponseType.CHART,
            content={
                "type": chart_type,  # line, bar, pie, scatter, etc.
                "data": data,
                "title": title,
            },
            summary=summary or f"Chart generated from {source}",
            metadata=ResponseMetadata(source=source, timestamp=datetime.utcnow().isoformat()),
        )

    @classmethod
    def image(
        cls,
        image_url: str,
        source: str = "generated",
        description: str | None = None,
        metadata_dict: dict | None = None,
    ) -> StructuredResponse:
        """Create an image response."""
        return cls(
            type=ResponseType.IMAGE,
            content={
                "url": image_url,
                "description": description,
            },
            summary=description or "Image response",
            metadata=ResponseMetadata(source=source, timestamp=datetime.utcnow().isoformat()),
        )

    @classmethod
    def from_existing_json(cls, existing_json: str) -> StructuredResponse | None:
        """
        Parse existing service response (usually JSON) and wrap it.

        This allows backwards compatibility with existing service outputs.
        """
        try:
            data = json.loads(existing_json)
        except (json.JSONDecodeError, TypeError):
            return None

        # Detect response type from existing data
        response_type = data.get("type", "text")

        if response_type == "table":
            return cls.table(
                columns=data.get("columns", []),
                rows=data.get("rows", []),
                title=data.get("title"),
                summary=data.get("summary"),
            )

        if response_type == "chart":
            return cls.chart(
                chart_type=data.get("chart_type", "unknown"),
                data=data.get("data", {}),
                title=data.get("title"),
            )

        # Default to text
        content = data.get("content") or str(data)
        return cls.text(content, summary=data.get("summary"))


def wrap_service_response(
    response: str | dict,
    source: str = "service",
    intent: str | None = None,
) -> StructuredResponse:
    """
    Wrap a service response (from existing services) into structured format.

    Args:
        response: Raw service response (JSON string or dict)
        source: Data source identifier
        intent: Detected intent

    Returns:
        StructuredResponse
    """
    # Handle already-structured responses
    if isinstance(response, str):
        wrapped = StructuredResponse.from_existing_json(response)
        if wrapped:
            if wrapped.metadata:
                wrapped.metadata.source = source
                wrapped.metadata.intent = intent
            return wrapped

        # Fallback: treat as text
        return StructuredResponse.text(response, source=source, summary=response[:200])

    # Handle dict responses
    if isinstance(response, dict):
        response_type = response.get("type", "text")

        if response_type == "table":
            return StructuredResponse.table(
                columns=response.get("columns", []),
                rows=response.get("rows", []),
                source=source,
                title=response.get("title"),
                summary=response.get("summary"),
            )

        if response_type == "chart":
            return StructuredResponse.chart(
                chart_type=response.get("chart_type", response.get("type", "line")),
                data=response.get("data", {}),
                source=source,
                title=response.get("title"),
                summary=response.get("summary"),
            )

        # Default: treat as text
        content = json.dumps(response, ensure_ascii=False)
        return StructuredResponse.text(content, source=source, summary=content[:200])

    # Unknown format
    return StructuredResponse.text(str(response), source=source)


def add_follow_ups(response: StructuredResponse, follow_ups: list[str]) -> StructuredResponse:
    """Add suggested follow-up questions to a response."""
    response.follow_ups = follow_ups
    return response


def merge_responses(responses: list[StructuredResponse]) -> StructuredResponse:
    """
    Merge multiple responses (from different sources) into one.

    Used for multi-intent queries that combine results from multiple APIs.
    """
    if not responses:
        return StructuredResponse.text("No responses to merge")

    if len(responses) == 1:
        return responses[0]

    # Merge text summaries
    summaries = [r.summary or str(r.content)[:100] for r in responses if r.summary]
    merged_summary = "\n\n".join(summaries)

    # Create hybrid response
    return StructuredResponse(
        type=ResponseType.HYBRID,
        content={
            "responses": [r.to_dict() for r in responses],
            "count": len(responses),
        },
        summary=merged_summary,
        metadata=ResponseMetadata(
            source="merged",
            timestamp=datetime.utcnow().isoformat(),
        ),
    )
