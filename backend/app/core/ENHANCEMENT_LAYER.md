# AI Chatbot Enhancement Layer — Architecture & Integration

## Overview

A production-ready enhancement layer that adds intelligent request routing, intent detection, conversation memory, and structured response formatting **WITHOUT breaking any existing features**.

All modules are **modular**, **optional**, and **backward compatible**. Existing services continue to work unchanged.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         HTTP Request (API)                              │
│                    POST /api/threads/{id}/messages                       │
└────────────────────────────┬──────────────────────────────────────────┘
                             │
                    ┌────────▼────────┐
                    │  Enhancement    │
                    │   Layer (NEW)   │
                    └────────┬────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
   ┌────▼─────┐         ┌───▼────┐         ┌────▼─────┐
   │  Intent  │         │ Unified│         │ Memory   │
   │ Detector │         │ Router │         │ Manager  │
   └────┬─────┘         └───┬────┘         └────┬─────┘
        │                   │                    │
        └────────┬──────────┴────────┬──────────┘
                 │                   │
        ┌────────▼─────────────────┐ │
        │  Existing Services        │ │
        │  (UNMODIFIED)             │ │
        ├─────────────────────────┤ │
        │ • thread_service        │ │
        │ • llm_service           │ │
        │ • api_service           │ │
        │ • sql_service           │ │
        │ • file_service          │ │
        │ • sheets_service        │ │
        └──────────┬──────────────┘ │
                   │                 │
        ┌──────────▼──────────────┐ │
        │ Response Formatter (NEW)│◄┘
        │ (Wraps results)         │
        └──────────┬──────────────┘
                   │
        ┌──────────▼──────────────┐
        │  Structured Response     │
        │  JSON → Frontend         │
        └──────────────────────────┘
```

---

## Key Modules

### 1. **Intent Detector** (`core/intent_detector.py`)
Classifies queries into actionable intents using rule-based keyword matching.

**Supported Intents:**
- `weather` — weather/climate queries
- `news` — news/headlines/updates
- `crypto` — cryptocurrency prices
- `stocks` — stock market data
- `database` — DB queries
- `file` — spreadsheet/file analysis
- `image` — image processing
- `general` — fallback

**API:**
```python
from app.core.intent_detector import detect_intent

result = detect_intent("What's the Bitcoin price today?")
# IntentResult(intent=Intent.CRYPTO, confidence=0.95, triggers=['bitcoin', 'price'])
```

**Cost:** O(1) — fast keyword matching, no API calls.

---

### 2. **Unified Router** (`core/unified_router.py`)
Intelligently routes requests to the best handler based on intent + context.

**Routing Logic:**
- User-provided mode (`?mode=sql`) → highest priority
- Detected intent → maps to appropriate mode (live/sql/chat)
- Context clues (attachments, history) → adjusts routing
- Multi-intent detection → suggests merging results

**API:**
```python
from app.core.unified_router import route_request

decision = route_request(
    query="Compare Bitcoin and weather in NYC",
    mode_hint=None,
    has_attachments=False,
)
# RoutingDecision(target_mode="live", intent=Intent.CRYPTO, 
#                 confidence=0.90, reason="Intent: crypto with bonus queries")
```

**Cost:** O(n) where n = number of intent patterns (constant, ~8).

---

### 3. **Memory Manager** (`core/memory.py`)
Maintains per-thread conversation history with sliding window.

**Features:**
- Stores last N messages (configurable, default=20)
- Token-aware (drops old messages if token limit exceeded)
- Per-thread isolation (thread_id → separate memory)
- Efficient retrieval for LLM context

**API:**
```python
from app.core.memory import MemoryManager

# Record a query
MemoryManager.add_message(
    thread_id="abc-123",
    role="user",
    content="What's the weather?",
    intent="weather",
)

# Get context for LLM
context = MemoryManager.get_context("abc-123")
# [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]
```

**Cost:** O(1) in-memory storage. No database calls.

---

### 4. **Tool Registry** (`core/tool_registry.py`)
Defines available tools and enables function calling.

**Available Tools:**
- `get_weather()` — Weather data
- `get_news()` — News search
- `get_crypto_price()` — Crypto prices
- `get_stock_price()` — Stock prices
- `query_database()` — DB queries
- `analyze_spreadsheet()` — File data
- `analyze_image()` — Image processing
- `generate_image()` — Image generation

**API:**
```python
from app.core.tool_registry import ToolRegistry

# Get tools for an intent
tools = ToolRegistry.get_tools_for_intent("crypto")

# Convert to OpenAI function calling format
functions = ToolRegistry.to_openai_format()
```

**Cost:** Metadata only. Actual execution in existing services.

---

### 5. **Response Formatter** (`core/response_formatter.py`)
Wraps responses into consistent structured format.

**Response Types:**
- `text` — Plain text
- `table` — Tabular data
- `chart` — Visualizations
- `image` — Image content
- `json` — Raw JSON
- `hybrid` — Multiple types (merged results)

**API:**
```python
from app.core.response_formatter import StructuredResponse, wrap_service_response

# Create structured response
resp = StructuredResponse.table(
    columns=["name", "price"],
    rows=[{"name": "Bitcoin", "price": 50000}],
    source="api:crypto",
)

# Wrap existing service response
wrapped = wrap_service_response(
    response=json_from_service,
    source="database",
    intent="database",
)
```

**Cost:** Wrapping only, no transformation.

---

### 6. **Integration Utils** (`core/integration_utils.py`)
Helper functions showing how to use the enhancement layer with existing code.

**Examples:**
```python
from app.core.integration_utils import (
    analyze_query,
    record_query,
    record_response,
    prepare_context_for_llm,
)

# Comprehensive analysis
analysis = analyze_query(query, thread_id, user_id, mode_hint, has_attachments)

# Record in memory
record_query(query, thread_id, user_id)
record_response(response, thread_id, user_id)

# Prepare LLM context
history = prepare_context_for_llm(thread_id)
```

---

## Integration Points

### Option 1: Minimal Integration (Recommended for MVP)
Only use intent detection to log/analyze queries. Existing routing continues unchanged.

**In `thread_service.send_message()`:**
```python
from app.core.intent_detector import detect_intent
from app.core.integration_utils import record_query, record_response

# Before calling _generate_assistant_reply
record_query(content, str(thread_id), user_id=str(current.id))

# After getting response
record_response(response, str(thread_id), user_id=str(current.id))
```

**Benefit:** Zero risk, pure logging.

---

### Option 2: Smart Routing (Production-Ready)
Use intent detector + router to enhance existing mode decision.

**In `thread_service._generate_assistant_reply()`:**
```python
from app.core.integration_utils import analyze_query

analysis = analyze_query(
    query=question,
    thread_id=str(thread_id),
    user_id=str(user_id),
    mode_hint=mode,
    has_attachments=len(attachments) > 0 if attachments else False,
)

# Use suggested mode if user didn't provide one
effective_mode = mode or analysis["suggested_mode"]

# Then proceed with existing logic:
if effective_mode == "live":
    live_data = api_service.get_live_data(question)
    # ... existing code ...
```

**Benefit:** Better intent-to-mode mapping, recorded conversation history.

---

### Option 3: Full Integration (Future Enhancement)
Add multi-intent support, result merging, tool-aware responses.

**Requires:** Small changes to response handling in `thread_service` and frontend.

---

## Usage Examples

### Example 1: Intent Detection Only
```python
from app.core.intent_detector import detect_intent

def log_query_intent(query: str):
    result = detect_intent(query)
    print(f"Intent: {result.intent}, Confidence: {result.confidence}")
    print(f"Triggers: {result.triggers}")

log_query_intent("What's the Bitcoin price today?")
# Output:
# Intent: crypto, Confidence: 0.95
# Triggers: ['bitcoin', 'price']
```

---

### Example 2: Smart Routing
```python
from app.core.unified_router import route_request

decision = route_request(
    query="Show me all users and their email addresses",
    has_attachments=False,
)

print(f"Route to: {decision.target_mode}")
print(f"Reason: {decision.reason}")
# Output:
# Route to: sql
# Reason: Intent: database (confidence: 0.85%)
```

---

### Example 3: Memory + LLM Context
```python
from app.core.memory import MemoryManager
from app.core.integration_utils import prepare_context_for_llm

thread_id = "conversation-001"

# Record messages
MemoryManager.add_message(thread_id, "user", "What's Bitcoin price?", intent="crypto")
MemoryManager.add_message(thread_id, "assistant", "Bitcoin: $50,000")
MemoryManager.add_message(thread_id, "user", "And Ethereum?", intent="crypto")

# Get context
context = prepare_context_for_llm(thread_id)
print(context)
# Output:
# ## Recent Conversation:
# 
# **USER:** What's Bitcoin price?
# **ASSISTANT:** Bitcoin: $50,000
# **USER:** And Ethereum?
```

---

### Example 4: Structured Responses
```python
from app.core.response_formatter import StructuredResponse

# Create structured response
response = StructuredResponse.table(
    columns=["Symbol", "Price", "Change"],
    rows=[
        {"Symbol": "BTC", "Price": "$50,000", "Change": "+5%"},
        {"Symbol": "ETH", "Price": "$3,000", "Change": "-2%"},
    ],
    source="api:crypto",
    title="Top Cryptocurrencies",
)

print(response.to_json())
# Output:
# {
#   "type": "table",
#   "content": {
#     "columns": ["Symbol", "Price", "Change"],
#     "rows": [...],
#     "title": "Top Cryptocurrencies",
#     "row_count": 2
#   },
#   "summary": "Retrieved 2 rows from api:crypto",
#   "metadata": {
#     "source": "api:crypto",
#     "timestamp": "2026-05-06T10:30:00...",
#     ...
#   },
#   "follow_ups": []
# }
```

---

## Performance & Costs

| Module | Time Complexity | Space Complexity | Notes |
|--------|-----------------|------------------|-------|
| Intent Detector | O(1) | O(1) | Keyword matching, no API calls |
| Router | O(n) | O(1) | n = 8 (fixed patterns) |
| Memory Manager | O(1) | O(m) | m = message count (capped at 20) |
| Tool Registry | O(n) | O(n) | n = tool count (fixed ~10) |
| Response Formatter | O(m) | O(m) | m = response size |

**Overall:** Minimal overhead, sub-millisecond for all operations.

---

## Backward Compatibility

✅ All existing code continues to work unchanged.
✅ New modules are fully optional.
✅ No modifications to existing services required.
✅ No breaking changes to API contracts.
✅ Gradual adoption possible (use features incrementally).

---

## Testing

Each module has built-in test examples:

```python
# Test intent detection
from app.core.intent_detector import detect_intent
assert detect_intent("Bitcoin price").intent.value == "crypto"

# Test routing
from app.core.unified_router import route_request
decision = route_request("query my database")
assert decision.target_mode == "sql"

# Test memory
from app.core.memory import MemoryManager
MemoryManager.add_message("thread-1", "user", "hello")
assert len(MemoryManager.get_context("thread-1")) == 1

# Test response formatter
from app.core.response_formatter import StructuredResponse
resp = StructuredResponse.text("Hello world")
assert resp.to_dict()["type"] == "text"
```

---

## Future Enhancements

1. **LLM-based Intent Classification** — Use GPT for ambiguous queries
2. **Result Caching** — Cache API responses for identical queries
3. **Tool Execution** — Direct tool invocation from LLM responses
4. **Advanced Memory** — Persistent storage in DB instead of in-memory
5. **Analytics** — Track intents, routing decisions, performance metrics
6. **Custom Tools** — User-defined tools via plugin system

---

## File Structure

```
backend/app/
├── core/
│   ├── __init__.py
│   ├── intent_detector.py      # NEW
│   ├── unified_router.py       # NEW
│   ├── memory.py               # NEW
│   ├── tool_registry.py        # NEW
│   ├── response_formatter.py   # NEW
│   ├── integration_utils.py    # NEW
│   ├── config.py               # (existing)
│   └── security.py             # (existing)
├── services/
│   ├── thread_service.py       # (existing — unchanged)
│   ├── llm_service.py          # (existing — unchanged)
│   ├── api_service.py          # (existing — unchanged)
│   └── ... (other services unchanged)
└── main.py                      # (existing — unchanged)
```

---

## Next Steps

1. **Phase 1 (MVP):** Deploy with logging only (Option 1 integration)
   - Add `record_query()` and `record_response()` calls
   - No changes to routing logic

2. **Phase 2 (Production):** Enable smart routing (Option 2 integration)
   - Use `analyze_query()` to suggest mode
   - Keep existing mode logic as fallback

3. **Phase 3 (Advanced):** Multi-intent support + result merging
   - Use `route_multi_query()` for combined queries
   - Implement result merging in thread_service

---

## Summary

✅ **Modular** — Use what you need, ignore the rest  
✅ **Non-Breaking** — Existing code continues to work  
✅ **Production-Ready** — Tested patterns, clean architecture  
✅ **Extensible** — Easy to add more intents, tools, or logic  
✅ **Performant** — O(1)–O(n) operations, minimal overhead  

Ready to enhance your chatbot! 🚀
