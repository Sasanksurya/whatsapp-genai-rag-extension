"""
Supervisor Agent.

Routes a resolved (self-contained) query to the right downstream
agent. Kept as a single cheap LLM classification call rather than a
heavier framework — this is the seam where Phase 4 will add MCP
routing (web/drive) as a third option.
"""
from typing import Literal

from app.llm.groq_client import llm_gateway

Route = Literal["document_query", "general_chat"]

ROUTE_SYSTEM_PROMPT = (
    "Classify the user's question into exactly one category:\n"
    "- document_query: requires looking up facts in the user's uploaded "
    "documents (registrations, contracts, files, records, 'the document', "
    "specific names/dates/numbers that would come from a file)\n"
    "- general_chat: general conversation, greetings, requests to draft/write "
    "a message, or anything not requiring document lookup\n\n"
    "Respond with ONLY one word: document_query or general_chat"
)


def route_query(resolved_query: str) -> Route:
    result = llm_gateway.generate(ROUTE_SYSTEM_PROMPT, resolved_query)
    normalized = result.strip().lower()
    if "document_query" in normalized:
        return "document_query"
    return "general_chat"
