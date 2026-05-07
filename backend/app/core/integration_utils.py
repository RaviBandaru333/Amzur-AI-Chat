"""Integration utilities — shows how to use the enhancement layer with existing code.

These are reference utilities (not required) for integrating the new modules
with the existing thread_service, llm_service, etc.
"""

from __future__ import annotations

from app.core.intent_detector import Intent, detect_intent, map_intent_to_mode
from app.core.memory import ConversationMemory, MemoryManager
from app.core.response_formatter import StructuredResponse, wrap_service_response
from app.core.tool_registry import ToolRegistry
from app.core.unified_router import route_request, RoutingDecision


def analyze_query(
    query: str,
    thread_id: str | None = None,
    user_id: str | None = None,
    mode_hint: str | None = None,
    has_attachments: bool = False,
) -> dict:
    """
    Comprehensive query analysis — combines all enhancement modules.

    Returns a dictionary with:
    - detected_intent: Intent object
    - routing_decision: RoutingDecision
    - available_tools: List of recommended tools
    - conversation_context: Recent message history
    - suggested_mode: Recommended execution mode

    Example usage in thread_service._generate_assistant_reply():

        analysis = analyze_query(
            query=prompt,
            thread_id=str(thread_id),
            user_id=str(user_id),
            mode_hint=mode,
            has_attachments=bool(attachments)
        )

        # Use analysis.suggested_mode to guide routing (already does this)
        # Use analysis.detected_intent for custom logic
        # Use analysis.available_tools for tool-aware responses
    """

    # Detect intent
    intent_result = detect_intent(query)

    # Route request
    routing_decision = route_request(
        query=query,
        mode_hint=mode_hint,
        history_length=0,  # Updated below if thread_id provided
        has_attachments=has_attachments,
    )

    # Get conversation context
    conversation_context = []
    if thread_id:
        memory = MemoryManager.get_memory(thread_id, user_id=user_id)
        conversation_context = memory.get_context_for_llm()
        routing_decision.metadata["history_length"] = len(memory.messages)

    # Get tools for detected intent
    available_tools = ToolRegistry.get_tools_for_intent(intent_result.intent.value)

    return {
        "detected_intent": intent_result.intent.value,
        "intent_triggers": intent_result.triggers,
        "intent_confidence": intent_result.confidence,
        "routing_decision": routing_decision.target_mode,
        "routing_reason": routing_decision.reason,
        "available_tools": [t.to_dict() for t in available_tools],
        "conversation_context": conversation_context,
        "suggested_mode": routing_decision.target_mode,
    }


def record_query(
    query: str,
    thread_id: str,
    user_id: str | None = None,
) -> None:
    """Record a user query in conversation memory."""
    intent_result = detect_intent(query)
    MemoryManager.add_message(
        thread_id=thread_id,
        role="user",
        content=query,
        intent=intent_result.intent.value,
        user_id=user_id,
    )


def record_response(
    response: str,
    thread_id: str,
    user_id: str | None = None,
) -> None:
    """Record an assistant response in conversation memory."""
    MemoryManager.add_message(
        thread_id=thread_id,
        role="assistant",
        content=response[:1000],  # Limit to avoid huge memory
        user_id=user_id,
    )


def prepare_context_for_llm(thread_id: str) -> str:
    """
    Prepare formatted conversation context for LLM system/user prompts.

    Can be injected into existing chat.txt or llm_service prompts.
    """
    memory = MemoryManager.get_memory(thread_id)
    context_messages = memory.get_context_for_llm()

    if not context_messages:
        return "No prior conversation history."

    lines = ["## Recent Conversation:\n"]
    for msg in context_messages[-10:]:  # Last 10 messages
        role = msg.get("role", "").upper()
        content = msg.get("content", "")[:300]
        lines.append(f"\n**{role}:** {content}")

    return "\n".join(lines)


# Example: How to use these in existing code
"""
# In thread_service._generate_assistant_reply() after detecting intent:

    from app.core.integration_utils import analyze_query, record_query, record_response

    # Analyze query comprehensively
    analysis = analyze_query(
        query=question,
        thread_id=str(thread_id),
        user_id=str(user_id),
        mode_hint=mode,
        has_attachments=has_attachments
    )

    # Record in memory
    record_query(question, str(thread_id), user_id=str(user_id))

    # Use suggested_mode to guide routing (already does this internally)
    mode_to_use = mode or analysis["suggested_mode"]

    # ... rest of existing logic ...

    # Record response
    record_response(answer, str(thread_id), user_id=str(user_id))


# In llm_service.ask_llm() to include conversation context:

    from app.core.integration_utils import prepare_context_for_llm

    history_context = prepare_context_for_llm(thread_id)

    user_prompt = (
        f"{history_context}\\n\\n"
        f"Current query: {query}\\n\\n"
        f"Real-time data provided:\\n{live_data}"
    )
"""
