"""/api/sql — NL-to-SQL generation and read-only execution."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db import get_db
from app.models import User
from app.schemas.sql import SQLAskRequest, SQLAskResponse, SQLGenerateRequest, SQLGenerateResponse
from app.services import sql_service

router = APIRouter(prefix="/api/sql", tags=["sql"])


@router.post("/generate", response_model=SQLGenerateResponse)
async def generate_sql(
    req: SQLGenerateRequest,
    _: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_user),
):
    sql = sql_service.generate_sql(
        question=req.question,
        user_email=current.email,
        model=req.model,
    )
    return SQLGenerateResponse(sql=sql)


@router.post("/ask", response_model=SQLAskResponse)
async def ask_sql(
    req: SQLAskRequest,
    _: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_user),
):
    sql, columns, rows = sql_service.ask_database(
        question=req.question,
        user_email=current.email,
        model=req.model,
        limit=req.limit,
    )
    return SQLAskResponse(
        sql=sql,
        columns=columns,
        rows=rows,
        row_count=len(rows),
    )
