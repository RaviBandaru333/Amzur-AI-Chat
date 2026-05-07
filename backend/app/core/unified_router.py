"""Unified routing layer — intelligent request dispatch based on intent + context.

This module decides which handler to use for a query without modifying
the existing thread_service logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.intent_detector import Intent, IntentResult, detect_intent, map_intent_to_mode


@dataclass
class RoutingDecision:
    """Result of routing analysis."""

    target_mode: str  # "chat", "sql", "live", "hybrid"
    intent: Intent
    confidence: float
    reason: str  # Human-readable explanation
    metadata: dict = None
    requires_multi_fetch: bool = False  # Whether multiple API calls needed

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


def route_request(
    query: str,
    mode_hint: str | None = None,
    history_length: int = 0,
    has_attachments: bool = False,
) -> RoutingDecision:
    """
    Intelligently route a request based on query content and context.

    This function does NOT modify existing behavior — it provides routing
    guidance that complements the existing thread_service logic.

    Args:
        query: User input
        mode_hint: User-provided mode preference ("chat", "sql", "live")
        history_length: Number of prior messages in thread (for follow-up detection)
        has_attachments: Whether message has attached files

    Returns:
        RoutingDecision with target mode and reasoning
    """
    if not query or not isinstance(query, str):
        return RoutingDecision(
            target_mode="chat",
            intent=Intent.GENERAL,
            confidence=0.0,
            reason="Empty query — using default chat mode",
        )

    # User-explicit mode takes priority
    if mode_hint and mode_hint.lower() in {"chat", "sql", "live"}:
        return RoutingDecision(
            target_mode=mode_hint.lower(),
            intent=Intent.GENERAL,
            confidence=1.0,
            reason=f"User explicitly selected {mode_hint.lower()} mode",
        )

    # Detect intent from query
    intent_result = detect_intent(query)
    target_mode = map_intent_to_mode(intent_result.intent) or "chat"

    # Adjust mode based on context
    if has_attachments and intent_result.intent != Intent.IMAGE:
        # If user uploaded files (and it's not an image query), prefer SQL mode
        if intent_result.intent in {Intent.GENERAL, Intent.DATABASE, Intent.FILE}:
            target_mode = "sql"
            reason = "Attachments detected — routing to SQL mode for file analysis"
        else:
            reason = f"Intent: {intent_result.intent.value} with attachments"
    else:
        reason = f"Intent: {intent_result.intent.value} (confidence: {intent_result.confidence:.0%})"

    return RoutingDecision(
        target_mode=target_mode,
        intent=intent_result.intent,
        confidence=intent_result.confidence,
        reason=reason,
        metadata={
            "triggers": intent_result.triggers,
            "has_attachments": has_attachments,
            "is_followup": history_length > 0,
        },
    )


def route_multi_query(query: str) -> list[RoutingDecision]:
    """
    For complex queries that may need multiple data sources.

    Example:
        "Compare Bitcoin price and current weather" → [CRYPTO routing, WEATHER routing]

    Args:
        query: User input

    Returns:
        List of routing decisions for each detected intent (confidence ≥ 0.6)
    """
    from app.core.intent_detector import detect_multi_intent

    multi_intents = detect_multi_intent(query, threshold=0.6)

    decisions = []
    for intent_result in multi_intents:
        target_mode = map_intent_to_mode(intent_result.intent) or "chat"
        decisions.append(
            RoutingDecision(
                target_mode=target_mode,
                intent=intent_result.intent,
                confidence=intent_result.confidence,
                reason=f"Multi-intent detection: {intent_result.intent.value}",
                metadata={"triggers": intent_result.triggers},
                requires_multi_fetch=len(multi_intents) > 1,
            )
        )

    return decisions


def should_merge_results(decisions: list[RoutingDecision]) -> bool:
    """
    Determine if results from multiple intents should be merged.

    Returns True if the query has multiple data-fetching intents that complement each other.
    """
    if len(decisions) < 2:
        return False

    # Merge if both are live intents
    live_intents = [d.intent for d in decisions if d.target_mode == "live"]
    if len(live_intents) >= 2:
        return True

    # Don't merge chat with other modes (chat is the fallback)
    if any(d.intent == Intent.GENERAL for d in decisions):
        return False

    return False


def explain_routing(decision: RoutingDecision) -> str:
    """Generate user-friendly explanation of routing decision."""
    return (
        f"🎯 Routing: {decision.target_mode.upper()} mode\n"
        f"📍 Reason: {decision.reason}\n"
        f"💪 Confidence: {decision.confidence:.0%}"
    )
