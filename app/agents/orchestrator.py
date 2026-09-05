"""
Orchestrator — runs one full conversational turn through the agent
pipeline:

  Conversation Agent (resolve references)
        -> retrieve candidate chunks (if this owner has any documents)
        -> Supervisor Agent (route) + relevance override
        -> RAG pipeline  OR  general chat
        -> Verification Agent (only for RAG answers)

ROUTING FIX (found via real-world testing): the Supervisor's LLM
classification alone was found to misroute clearly document-related
questions (e.g. "What skills does he have?") to general_chat, which
skipped retrieval entirely and let the model hallucinate freely from
conversation history instead of the actual resume. A small
classifier model guessing intent from text alone isn't reliable
enough to gate RAG access on its own.

The fix: retrieve candidate chunks FIRST (cheap — it's a local
vector search, not an LLM call), and if any hit is strongly relevant
(low cosine distance), route to RAG regardless of what the
classifier said. The classifier is still used for the case where
there ARE no strong hits — to distinguish "general chat" from
"document question with no matching content" — but it can no longer
be the single point of failure that causes silent hallucination.
"""
from app.agents.conversation_agent import resolve_query
from app.agents.supervisor_agent import route_query
from app.agents.verification_agent import correct_answer, verify_answer
from app.conversation.store import conversation_store
from app.core.config import settings
from app.llm.groq_client import llm_gateway
from app.rag.pipeline import answer_from_hits, retrieve
from app.rag.vectorstore import vector_store

GENERAL_CHAT_SYSTEM_PROMPT = (
    "You are a helpful assistant embedded in a WhatsApp conversation "
    "workflow. Use the conversation history for context. Keep replies "
    "concise and natural for a chat interface."
)


def _has_strong_hit(hits: list[dict]) -> bool:
    return any(h["distance"] <= settings.relevance_distance_threshold for h in hits)


def handle_turn(conversation_id: str, owner_id: str, message: str) -> dict:
    conversation_store.add_turn(conversation_id, "user", message)

    resolved_query = resolve_query(conversation_id, message)

    # Only bother retrieving if this owner has indexed anything at all —
    # avoids a pointless vector search + keeps plain chit-chat fast.
    has_documents = bool(vector_store.list_documents(owner_id))
    hits: list[dict] = []
    if has_documents:
        hits = retrieve(resolved_query, owner_id)

    llm_route = route_query(resolved_query)
    use_rag = has_documents and (llm_route == "document_query" or _has_strong_hit(hits))

    if use_rag:
        rag_result = answer_from_hits(hits, resolved_query)
        verification = verify_answer(rag_result["answer"], rag_result["context"])

        reply = rag_result["answer"]
        if not verification["verified"]:
            # Don't just flag hallucinated content — actually re-ground it.
            reply = correct_answer(reply, rag_result["context"], resolved_query)
            verification = verify_answer(reply, rag_result["context"])
            if not verification["verified"] and verification["note"]:
                reply += f"\n\n⚠️ Note: {verification['note']}"

        conversation_store.add_turn(conversation_id, "assistant", reply)
        return {
            "reply": reply,
            "agent_used": "rag_agent",
            "resolved_query": resolved_query,
            "sources": rag_result["sources"],
            "verified": verification["verified"],
        }

    # general_chat route
    history_text = conversation_store.as_text(conversation_id, limit=6)
    prompt = f"Conversation history:\n{history_text}\n\nUser: {message}"
    reply = llm_gateway.generate(GENERAL_CHAT_SYSTEM_PROMPT, prompt)

    conversation_store.add_turn(conversation_id, "assistant", reply)
    return {
        "reply": reply,
        "agent_used": "conversation_agent",
        "resolved_query": resolved_query,
        "sources": [],
        "verified": None,
    }
