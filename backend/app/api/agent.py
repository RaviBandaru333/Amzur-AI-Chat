"""/api/agent — LangChain ReAct agent with live-data tools.

Two endpoints:
    POST /api/agent/chat        — synchronous JSON {answer, steps}
    GET  /api/agent/chat/stream — Server-Sent Events for "AI is thinking…" UI

The agent autonomously selects which of `get_weather`, `get_crypto`, `get_news`
to call and may chain multiple calls in a single user turn. No if/else routing.
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.ai.agents.live_agent import event_to_sse, run_agent, stream_agent
from app.core.security import get_current_user
from app.models import User


router = APIRouter(prefix="/api/agent", tags=["agent"])


class AgentChatRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)


class AgentStep(BaseModel):
    tool: str
    tool_input: Any
    log: str
    observation: str


class AgentChatResponse(BaseModel):
    ok: bool
    answer: str
    steps: list[AgentStep]


@router.post("/chat", response_model=AgentChatResponse)
async def agent_chat(
    req: AgentChatRequest,
    current: User = Depends(get_current_user),
) -> AgentChatResponse:
    """Run the agent synchronously. Returns the final answer plus the
    intermediate ReAct steps so the UI can render the reasoning trail."""
    result = run_agent(req.query, user_email=current.email)
    return AgentChatResponse(
        ok=bool(result.get("ok")),
        answer=result.get("answer", ""),
        steps=[AgentStep(**step) for step in result.get("steps", [])],
    )


@router.get("/chat/stream")
async def agent_chat_stream(
    query: str = Query(..., min_length=1, max_length=2000),
    current: User = Depends(get_current_user),
) -> StreamingResponse:
    """Stream agent progress as Server-Sent Events.

    Event types: thinking | tool_start | tool_end | final | error.
    Each event is a JSON object: `{"type": ..., "data": {...}}`.
    """
    async def _gen():
        # Initial heartbeat so the client knows the connection is alive.
        yield b": ping\n\n"
        async for event in stream_agent(query, user_email=current.email):
            yield event_to_sse(event)
        # Final SSE event consumed by EventSource clients to close cleanly.
        yield b"event: done\ndata: {}\n\n"

    return StreamingResponse(
        _gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# Helper retained for symmetry with other routers — not currently used.
def _to_json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)
