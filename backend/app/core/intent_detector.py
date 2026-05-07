"""Intent detection layer — classify user queries into actionable intents.

This module uses rule-based keyword matching for fast, deterministic detection
and optionally uses LLM for ambiguous queries. Keeps existing routing logic intact.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Intent(str, Enum):
    """Supported intent types."""

    WEATHER = "weather"
    NEWS = "news"
    CRYPTO = "crypto"
    STOCKS = "stocks"
    DATABASE = "database"
    FILE = "file"
    IMAGE = "image"
    GENERAL = "general"
    HELP = "help"


@dataclass
class IntentResult:
    """Result of intent detection."""

    intent: Intent
    confidence: float  # 0.0 to 1.0
    triggers: list[str]  # Keywords that triggered detection
    metadata: dict = None  # Additional context (e.g., "domain": "crypto")

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


# Rule-based keyword patterns for fast detection.
_INTENT_PATTERNS = {
    Intent.WEATHER: {
        "keywords": ["weather", "temperature", "rain", "snow", "forecast", "wind", "humidity", "climate"],
        "phrases": ["weather today", "current weather", "weather forecast"],
        "confidence": 0.95,
    },
    Intent.NEWS: {
        "keywords": ["news", "headline", "breaking", "latest", "headlines", "article", "press", "report"],
        "phrases": ["breaking news", "latest news", "headlines today", "news today"],
        "confidence": 0.90,
    },
    Intent.CRYPTO: {
        "keywords": ["bitcoin", "ethereum", "crypto", "cryptocurrency", "btc", "eth", "blockchain", "wallet"],
        "phrases": ["bitcoin price", "ethereum price", "crypto market"],
        "confidence": 0.95,
    },
    Intent.STOCKS: {
        "keywords": ["stock", "share", "reliance", "tcs", "infy", "sensex", "nifty", "market", "trading"],
        "phrases": ["stock price", "share price", "market today", "nifty 50"],
        "confidence": 0.90,
    },
    Intent.DATABASE: {
        "keywords": ["query", "database", "table", "record", "select", "count", "sum", "average", "column"],
        "phrases": ["how many", "list all", "show me", "get from database"],
        "confidence": 0.85,
    },
    Intent.FILE: {
        "keywords": ["excel", "spreadsheet", "csv", "data", "file", "upload", "sheet", "row", "column"],
        "phrases": ["excel file", "spreadsheet", "uploaded file", "attached file"],
        "confidence": 0.90,
    },
    Intent.IMAGE: {
        "keywords": ["image", "picture", "photo", "screenshot", "visual", "diagram", "chart", "graph"],
        "phrases": ["analyze image", "describe image", "what's in this"],
        "confidence": 0.90,
    },
    Intent.HELP: {
        "keywords": ["help", "how to", "what can you do", "capabilities", "features"],
        "phrases": ["help me", "how do i", "what can you"],
        "confidence": 0.85,
    },
}


def detect_intent(query: str) -> IntentResult:
    """
    Detect user intent from a query string using rule-based matching.

    Args:
        query: User input query

    Returns:
        IntentResult with detected intent and metadata
    """
    if not query or not isinstance(query, str):
        return IntentResult(intent=Intent.GENERAL, confidence=0.0, triggers=[])

    query_lower = query.lower().strip()
    best_intent = Intent.GENERAL
    best_confidence = 0.0
    best_triggers = []

    for intent, patterns in _INTENT_PATTERNS.items():
        triggers = []
        confidence = 0.0

        # Check phrases first (higher weight)
        for phrase in patterns.get("phrases", []):
            if phrase in query_lower:
                triggers.append(phrase)
                confidence = patterns.get("confidence", 0.8)
                break

        # If no phrase match, check keywords
        if not triggers:
            matched_keywords = [kw for kw in patterns.get("keywords", []) if kw in query_lower]
            if matched_keywords:
                triggers = matched_keywords[:3]  # Top 3 keywords
                confidence = patterns.get("confidence", 0.8) * 0.85  # Slightly lower for keyword-only

        # Update best match
        if confidence > best_confidence:
            best_confidence = confidence
            best_intent = intent
            best_triggers = triggers

    return IntentResult(
        intent=best_intent,
        confidence=best_confidence,
        triggers=best_triggers,
        metadata={"query_length": len(query_lower), "detected_at": "keyword_matching"},
    )


def detect_multi_intent(query: str, threshold: float = 0.6) -> list[IntentResult]:
    """
    Detect multiple possible intents for complex queries.

    Example:
        "Compare Bitcoin price and weather" → [CRYPTO, WEATHER]

    Args:
        query: User input query
        threshold: Confidence threshold for inclusion

    Returns:
        List of IntentResults sorted by confidence (descending)
    """
    if not query or not isinstance(query, str):
        return []

    query_lower = query.lower().strip()
    results = []

    for intent, patterns in _INTENT_PATTERNS.items():
        triggers = []
        confidence = 0.0

        # Check phrases first
        for phrase in patterns.get("phrases", []):
            if phrase in query_lower:
                triggers.append(phrase)
                confidence = patterns.get("confidence", 0.8)
                break

        # If no phrase match, check keywords
        if not triggers:
            matched_keywords = [kw for kw in patterns.get("keywords", []) if kw in query_lower]
            if matched_keywords:
                triggers = matched_keywords[:3]
                confidence = patterns.get("confidence", 0.8) * 0.85

        if confidence >= threshold:
            results.append(
                IntentResult(
                    intent=intent,
                    confidence=confidence,
                    triggers=triggers,
                    metadata={"detected_at": "keyword_matching"},
                )
            )

    # Sort by confidence (highest first)
    results.sort(key=lambda r: r.confidence, reverse=True)
    return results


def map_intent_to_mode(intent: Intent) -> str | None:
    """
    Map detected intent to execution mode.

    Intent → Mode mapping:
    - WEATHER/NEWS/CRYPTO/STOCKS → "live"
    - DATABASE → "sql"
    - FILE → "sql" (uses file_service)
    - IMAGE → "chat" (uses image utils)
    - GENERAL/HELP → "chat"

    Args:
        intent: Detected intent

    Returns:
        Mode string ("chat", "sql", "live") or None to use default logic
    """
    mode_map = {
        Intent.WEATHER: "live",
        Intent.NEWS: "live",
        Intent.CRYPTO: "live",
        Intent.STOCKS: "live",
        Intent.DATABASE: "sql",
        Intent.FILE: "sql",
        Intent.IMAGE: "chat",
        Intent.GENERAL: "chat",
        Intent.HELP: "chat",
    }
    return mode_map.get(intent)
