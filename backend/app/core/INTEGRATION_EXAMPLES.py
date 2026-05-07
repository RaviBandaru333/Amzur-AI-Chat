"""Example integrations — copy/paste ready code snippets for using the enhancement layer.

These are production-ready examples that can be dropped into existing services
without modifying the services themselves.
"""

# ─────────────────────────────────────────────────────────────────────────
# EXAMPLE 1: Add Intent Logging to thread_service.send_message()
# ─────────────────────────────────────────────────────────────────────────

"""
In thread_service.py, find send_message() function and add:

from app.core.integration_utils import record_query, record_response

async def send_message(db: AsyncSession, current: User, thread_id: uuid.UUID, ...):
    # ... existing validation code ...

    # NEW: Record query in memory
    try:
        record_query(content, str(thread_id), user_id=str(current.id))
    except Exception:
        pass  # Silently ignore memory errors

    # Call existing _generate_assistant_reply
    reply = await _generate_assistant_reply(
        client=client,
        llm_model=model or settings.LLM_MODEL,
        user_email=current.email,
        history=history_dicts,
        prompt=content,
        attachments=attachments,
        thread_id=str(thread_id),
        user_id=str(current.id),
        raw_prompt=raw_prompt,
        mode=mode,
    )

    # NEW: Record response in memory
    try:
        record_response(reply, str(thread_id), user_id=str(current.id))
    except Exception:
        pass

    # ... rest of existing code ...
"""


# ─────────────────────────────────────────────────────────────────────────
# EXAMPLE 2: Smart Mode Selection in _generate_assistant_reply()
# ─────────────────────────────────────────────────────────────────────────

"""
In thread_service.py, find _generate_assistant_reply() and modify the mode detection:

from app.core.integration_utils import analyze_query

def _generate_assistant_reply(
    *,
    client,
    llm_model: str,
    user_email: str,
    history: list[dict[str, str]],
    prompt: str,
    attachments: list[dict] | None = None,
    thread_id: str | None = None,
    user_id: str | None = None,
    raw_prompt: str | None = None,
    mode: str | None = None,
) -> str:
    '''Generate assistant output for chat, image, or embedding models.'''
    
    # NEW: Enhanced mode decision with analysis
    if not mode:
        analysis = analyze_query(
            query=prompt,
            thread_id=thread_id,
            user_id=user_id,
            mode_hint=None,
            has_attachments=bool(attachments),
        )
        # Use suggested mode as fallback
        suggested_mode = analysis.get("suggested_mode", "chat")
    else:
        suggested_mode = mode
    
    mtype = _model_type(llm_model)

    if mtype == "chat":
        mode_lower = (suggested_mode or "").lower()
        question = raw_prompt if isinstance(raw_prompt, str) else (prompt if isinstance(prompt, str) else str(prompt))

        # ── Live data mode ─────────────────────────────────────────────────────
        auto_live = any(kw in question.lower() for kw in _LIVE_AUTO_KEYWORDS)
        if mode_lower == "live" or auto_live:
            live_data = api_service.get_live_data(question)
            if live_data.get("has_data"):
                return llm_service.ask_llm(question, live_data, user_email=user_email, model=llm_model)
            if mode_lower == "live":
                return llm_service.ask_llm_fallback(question, user_email=user_email, model=llm_model)

        # ... rest of existing logic unchanged ...
"""


# ─────────────────────────────────────────────────────────────────────────
# EXAMPLE 3: Add Conversation Context to LLM Prompts
# ─────────────────────────────────────────────────────────────────────────

"""
In llm_service.py, modify ask_llm() user_prompt to include history:

from app.core.integration_utils import prepare_context_for_llm

def ask_llm(query: str, data: dict[str, Any], user_email: str, model: str | None = None, thread_id: str | None = None) -> str:
    '''Ask the model to filter, format, and interpret live API results intelligently.'''
    chosen = model or settings.LLM_MODEL
    client = get_llm_client()

    # ... existing system_prompt code ...

    focused_data = _prepare_live_context(query, data)
    
    # NEW: Get conversation context if thread_id provided
    history_context = ""
    if thread_id:
        try:
            history_context = prepare_context_for_llm(thread_id)
        except Exception:
            pass

    user_prompt = (
        history_context + "\\n\\n"  # NEW: Add history
        f"User Query:\\n{query}\\n\\n"
        "Real-time API Data (check this first — use it if relevant to the query):\\n"
        f"{_compact_json(focused_data, limit=12000)}\\n\\n"
        "Instructions:\\n"
        "- If the data answers the query: extract the relevant parts, show top 5-10 results, "
        "use bullets or paragraphs, end with [Source: <name> | Fetched: live]\\n"
        "- If the data does NOT answer the query: answer from your training knowledge normally.\\n"
        "- Never say 'No data found'. Always give the best answer you can."
    )

    response = client.chat.completions.create(
        model=chosen,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
        max_tokens=1200,
        user=user_email,
        **_tracking_without_user("live_data_filter_format"),
    )
    
    # ... rest of existing code ...
"""


# ─────────────────────────────────────────────────────────────────────────
# EXAMPLE 4: Wrap Service Responses with Structure
# ─────────────────────────────────────────────────────────────────────────

"""
In any service that returns responses, optionally wrap with structure:

from app.core.response_formatter import wrap_service_response

# In sql_service or thread_service, after getting a response:

response_json = json.dumps({
    "type": "table",
    "columns": ["id", "name"],
    "rows": [{"id": 1, "name": "Alice"}],
})

# Optionally wrap for structured format (backward compatible)
wrapped = wrap_service_response(
    response=response_json,
    source="database",
    intent="database",
)

# Original response still works:
return response_json

# Structured version available:
# return wrapped.to_json()
"""


# ─────────────────────────────────────────────────────────────────────────
# EXAMPLE 5: Add Intent-Based Tool Availability in Chat
# ─────────────────────────────────────────────────────────────────────────

"""
In frontend or API response, include available tools based on intent:

from app.core.tool_registry import ToolRegistry

def get_tools_for_query(query: str) -> list[dict]:
    '''Return available tools based on query intent.'''
    from app.core.intent_detector import detect_intent
    
    intent_result = detect_intent(query)
    tools = ToolRegistry.get_tools_for_intent(intent_result.intent.value)
    return [t.to_dict() for t in tools]

# Example usage in API response:
tools = get_tools_for_query("What's the Bitcoin price?")
# [
#   {
#     "id": "get_crypto_price",
#     "name": "Get Crypto Price",
#     "description": "Fetch current cryptocurrency prices...",
#     "parameters": [...]
#   }
# ]
"""


# ─────────────────────────────────────────────────────────────────────────
# EXAMPLE 6: Add Metadata to API Response
# ─────────────────────────────────────────────────────────────────────────

"""
In API responses (e.g., /api/threads/{id}/messages), add enhancement metadata:

from app.core.integration_utils import analyze_query

@router.post("/{thread_id}/messages", response_model=dict)
async def send_message(...):
    # ... existing code ...
    
    # NEW: Add enhancement metadata to response
    analysis = analyze_query(
        query=req.content,
        thread_id=str(thread_id),
        user_id=str(current.id),
        has_attachments=len(req.files) > 0 if req.files else False,
    )
    
    response_body = {
        "message": message_dict,
        "thread": thread_detail_dict,
        # NEW: Optional metadata (can be hidden in production)
        "_metadata": {
            "detected_intent": analysis["detected_intent"],
            "routing_mode": analysis["routing_decision"],
            "tools_available": analysis["available_tools"],
        }
    }
    
    return response_body
"""


# ─────────────────────────────────────────────────────────────────────────
# EXAMPLE 7: Add Conversation Memory Endpoint (Optional Admin/Debug)
# ─────────────────────────────────────────────────────────────────────────

"""
Add a debug endpoint to view conversation memory (optional, remove in production):

from fastapi import APIRouter
from app.core.memory import MemoryManager

router = APIRouter(prefix="/api/debug", tags=["debug"])

@router.get("/threads/{thread_id}/memory")
async def get_thread_memory(thread_id: str, current: User = Depends(get_current_user)):
    '''Get conversation memory for a thread (debug endpoint).'''
    stats = MemoryManager.get_stats(thread_id)
    memory = MemoryManager.get_memory(thread_id)
    
    return {
        "thread_id": thread_id,
        "stats": stats,
        "recent_messages": [m.to_dict() for m in memory.get_recent(5)],
    }

# Example response:
# {
#   "thread_id": "abc-123",
#   "stats": {
#     "total_messages": 5,
#     "user_messages": 3,
#     "assistant_messages": 2,
#     "estimated_tokens": 450,
#     "unique_intents": 2,
#     "intents": ["crypto", "news"]
#   },
#   "recent_messages": [
#     {"role": "user", "content": "What's Bitcoin price?"},
#     {"role": "assistant", "content": "Bitcoin: $50,000..."}
#   ]
# }
"""


# ─────────────────────────────────────────────────────────────────────────
# IMPLEMENTATION CHECKLIST
# ─────────────────────────────────────────────────────────────────────────

"""
Copy this checklist to track implementation progress:

□ Phase 1 — Logging Only (No Breaking Changes)
  □ Add record_query() call in thread_service.send_message()
  □ Add record_response() call after response is generated
  □ Test: Verify no errors, existing behavior unchanged
  
□ Phase 2 — Smart Routing (Enhanced Mode Selection)
  □ Add analyze_query() call in _generate_assistant_reply()
  □ Use suggested_mode as fallback
  □ Test: Verify routing decisions are reasonable
  
□ Phase 3 — Memory-Aware Prompts (Optional)
  □ Add prepare_context_for_llm() to llm_service prompts
  □ Test: Verify LLM uses conversation history
  
□ Phase 4 — Response Wrapping (Optional)
  □ Use wrap_service_response() for table/chart responses
  □ Test: Verify frontend can render wrapped responses
  
□ Phase 5 — Full Integration (Advanced)
  □ Implement multi-intent routing
  □ Add result merging for combined queries
  □ Add tool availability to frontend

Production Deployment:
□ Remove debug endpoints (EXAMPLE 7) or protect with admin role
□ Add error handling for enhancement layer
□ Monitor performance impact (should be <1ms)
□ Document in team wiki/docs
"""
