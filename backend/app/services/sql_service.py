"""Natural-language to SQL (read-only) service."""

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from functools import lru_cache
import re
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

from app.ai.llm import get_llm_client, tracking_kwargs
from app.core.config import settings

BLOCKED_SQL_KEYWORDS = ("INSERT", "UPDATE", "DELETE", "DROP", "TRUNCATE", "ALTER")
BLOCKED_SQL_RE = re.compile(r"\b(?:insert|update|delete|drop|truncate|alter)\b", re.IGNORECASE)


def _build_sync_db_url() -> str:
    if settings.DATABASE_URL_SYNC:
        return settings.DATABASE_URL_SYNC
    return settings.DATABASE_URL.replace("+asyncpg", "+psycopg2")


@lru_cache
def _get_engine() -> Engine:
    return create_engine(_build_sync_db_url(), future=True)


def _schema_overview() -> str:
    engine = _get_engine()
    insp = inspect(engine)
    table_names = insp.get_table_names()

    lines: list[str] = []
    for table in table_names[:80]:
        cols = insp.get_columns(table)
        col_parts: list[str] = []
        for col in cols[:40]:
            col_name = str(col.get("name", ""))
            col_type = str(col.get("type", ""))
            col_parts.append(f"{col_name} {col_type}")
        lines.append(f"{table}: {', '.join(col_parts)}")

    return "\n".join(lines)


def _clean_sql(raw: str) -> str:
    sql = (raw or "").strip()
    if sql.startswith("```"):
        sql = re.sub(r"^```(?:sql)?\s*", "", sql, flags=re.IGNORECASE)
        sql = re.sub(r"\s*```$", "", sql)
    return sql.strip().rstrip(";").strip()


def _is_select_only(sql: str) -> bool:
    if not sql:
        return False
    if BLOCKED_SQL_RE.search(sql):
        return False
    return bool(re.match(r"^(select\b|with\b[\s\S]*?\bselect\b)", sql, flags=re.IGNORECASE))


def _validated_sql(sql: str) -> str:
    cleaned = _clean_sql(sql)
    if not cleaned:
        raise HTTPException(status_code=400, detail={"error": "invalid_sql", "message": "Empty SQL generated"})

    if not _is_select_only(cleaned):
        raise HTTPException(
            status_code=400,
            detail={
                "error": "unsafe_sql",
                "message": "Only SELECT queries are allowed; write operations are blocked",
            },
        )

    return cleaned


def _jsonable(value: Any) -> Any:
    if isinstance(value, (datetime, date, time, Decimal, UUID)):
        return str(value)
    return value


def generate_sql(question: str, user_email: str, model: str | None = None) -> str:
    schema_text = _schema_overview()
    llm_model = model or settings.LLM_MODEL

    system_prompt = (
        "You are an expert SQL generator. "
        "Convert the user question into SQL using the provided schema. "
        "Rules: use ONLY SELECT queries; never modify data; "
        "never use INSERT, UPDATE, DELETE, DROP, TRUNCATE, ALTER; "
        "return ONLY SQL with no explanation."
    )

    user_prompt = (
        "Schema:\n"
        f"{schema_text}\n\n"
        "User Question:\n"
        f"{question}"
    )

    client = get_llm_client()
    resp = client.chat.completions.create(
        model=llm_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.0,
        max_tokens=500,
        user=user_email,
        **{k: v for k, v in tracking_kwargs("nl_to_sql").items() if k != "user"},
    )
    generated = resp.choices[0].message.content or ""
    return _validated_sql(generated)


def execute_select(sql: str, limit: int = 50) -> tuple[list[str], list[dict[str, Any]]]:
    safe_sql = _validated_sql(sql)
    bounded_limit = max(1, min(limit, 500))

    if not re.search(r"\blimit\s+\d+\b", safe_sql, flags=re.IGNORECASE):
        safe_sql = f"SELECT * FROM ({safe_sql}) AS generated_query LIMIT {bounded_limit}"

    engine = _get_engine()
    with engine.connect() as conn:
        result = conn.execute(text(safe_sql))
        rows = result.fetchall()
        columns = list(result.keys())

    payload_rows: list[dict[str, Any]] = []
    for row in rows:
        mapped = row._mapping
        payload_rows.append({key: _jsonable(mapped[key]) for key in columns})

    return columns, payload_rows


def ask_database(question: str, user_email: str, model: str | None = None, limit: int = 50) -> tuple[str, list[str], list[dict[str, Any]]]:
    sql = generate_sql(question=question, user_email=user_email, model=model)
    columns, rows = execute_select(sql=sql, limit=limit)
    return sql, columns, rows
