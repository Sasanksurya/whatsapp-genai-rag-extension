"""
Conversation history store.

In-memory for now (fine for a single-process demo). The interface is
deliberately small so swapping this for Redis/Postgres later (Phase 6
hardening) doesn't require touching any agent code — every agent only
talks to `conversation_store`, never to a raw dict.
"""
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class Turn:
    role: str  # "user" | "assistant"
    content: str


class ConversationStore:
    def __init__(self) -> None:
        self._history: dict[str, list[Turn]] = defaultdict(list)

    def add_turn(self, conversation_id: str, role: str, content: str) -> None:
        self._history[conversation_id].append(Turn(role=role, content=content))

    def get_recent(self, conversation_id: str, limit: int = 6) -> list[Turn]:
        return self._history[conversation_id][-limit:]

    def as_text(self, conversation_id: str, limit: int = 6) -> str:
        turns = self.get_recent(conversation_id, limit)
        if not turns:
            return "(no prior conversation)"
        return "\n".join(f"{t.role}: {t.content}" for t in turns)


conversation_store = ConversationStore()
