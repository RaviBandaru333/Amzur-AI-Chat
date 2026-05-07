"""Memory management — maintain and retrieve conversation context.

Handles conversation history, sliding window, and context summarization
to improve multi-turn understanding while respecting token limits.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Message:
    """Single message in conversation memory."""

    role: str  # "user" or "assistant"
    content: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    intent: str | None = None  # Detected intent
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dict for LLM consumption."""
        return {
            "role": self.role,
            "content": self.content,
        }

    def token_estimate(self, chars_per_token: int = 4) -> int:
        """Rough token count for context management."""
        return max(1, len(self.content) // chars_per_token)


@dataclass
class ConversationMemory:
    """Manages conversation history and context."""

    messages: list[Message] = field(default_factory=list)
    max_history_length: int = 20  # Max messages to retain
    max_context_tokens: int = 4000  # Token limit for LLM context
    user_id: str | None = None
    thread_id: str | None = None

    def add_message(
        self,
        role: str,
        content: str,
        intent: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        """Add a message to memory."""
        msg = Message(
            role=role,
            content=content,
            intent=intent,
            metadata=metadata or {},
        )
        self.messages.append(msg)

        # Enforce limits
        self._enforce_limits()

    def _enforce_limits(self) -> None:
        """Enforce max history and token limits."""
        # Drop oldest messages if over length limit
        if len(self.messages) > self.max_history_length:
            self.messages = self.messages[-self.max_history_length :]

        # Drop oldest messages if over token limit
        total_tokens = sum(m.token_estimate() for m in self.messages)
        while total_tokens > self.max_context_tokens and len(self.messages) > 2:
            dropped = self.messages.pop(0)
            total_tokens -= dropped.token_estimate()

    def get_recent(self, count: int = 5) -> list[Message]:
        """Get most recent N messages."""
        return self.messages[-count:]

    def get_context_for_llm(self, include_metadata: bool = False) -> list[dict]:
        """Get message history in LLM-compatible format."""
        messages = []
        for msg in self.messages:
            entry = msg.to_dict()
            if include_metadata and msg.metadata:
                entry["_metadata"] = msg.metadata
            messages.append(entry)
        return messages

    def get_summary_stats(self) -> dict:
        """Get conversation statistics."""
        user_msgs = [m for m in self.messages if m.role == "user"]
        assistant_msgs = [m for m in self.messages if m.role == "assistant"]
        total_tokens = sum(m.token_estimate() for m in self.messages)
        intents = [m.intent for m in user_msgs if m.intent]

        return {
            "total_messages": len(self.messages),
            "user_messages": len(user_msgs),
            "assistant_messages": len(assistant_msgs),
            "estimated_tokens": total_tokens,
            "unique_intents": len(set(intents)),
            "intents": list(set(intents)),
        }

    def clear(self) -> None:
        """Clear all messages."""
        self.messages = []

    def to_dict(self) -> dict:
        """Serialize memory to dict."""
        return {
            "user_id": self.user_id,
            "thread_id": self.thread_id,
            "messages": [m.to_dict() for m in self.messages],
            "stats": self.get_summary_stats(),
        }


class MemoryManager:
    """Global memory manager — maintains separate memory per thread."""

    _memories: dict[str, ConversationMemory] = {}

    @classmethod
    def get_memory(
        cls,
        thread_id: str,
        user_id: str | None = None,
        max_history: int = 20,
        max_tokens: int = 4000,
    ) -> ConversationMemory:
        """Get or create memory for a thread."""
        if thread_id not in cls._memories:
            cls._memories[thread_id] = ConversationMemory(
                user_id=user_id,
                thread_id=thread_id,
                max_history_length=max_history,
                max_context_tokens=max_tokens,
            )
        return cls._memories[thread_id]

    @classmethod
    def add_message(
        cls,
        thread_id: str,
        role: str,
        content: str,
        intent: str | None = None,
        user_id: str | None = None,
    ) -> None:
        """Add message to thread memory."""
        memory = cls.get_memory(thread_id, user_id=user_id)
        memory.add_message(role, content, intent=intent)

    @classmethod
    def get_context(cls, thread_id: str) -> list[dict]:
        """Get LLM context for a thread."""
        if thread_id not in cls._memories:
            return []
        return cls._memories[thread_id].get_context_for_llm()

    @classmethod
    def clear_memory(cls, thread_id: str) -> None:
        """Clear memory for a thread."""
        if thread_id in cls._memories:
            del cls._memories[thread_id]

    @classmethod
    def get_stats(cls, thread_id: str) -> dict:
        """Get stats for a thread."""
        if thread_id not in cls._memories:
            return {}
        return cls._memories[thread_id].get_summary_stats()


def build_history_context(messages: list[dict], max_messages: int = 10) -> str:
    """
    Build human-readable conversation history for LLM context.

    Args:
        messages: List of message dicts with role/content
        max_messages: Max recent messages to include

    Returns:
        Formatted history string
    """
    if not messages:
        return "No prior conversation history."

    recent = messages[-max_messages:]
    lines = ["## Conversation History\n"]

    for msg in recent:
        role = msg.get("role", "").upper()
        content = msg.get("content", "")[:500]  # Trim long messages
        lines.append(f"\n**{role}:** {content}")

    return "\n".join(lines)
