
"""
Orchestrator for conversation-aware document Q&A.

Document retrieval is scoped by:
    owner_id + conversation_id + optional document_id

Document questions should be grounded in retrieved context rather
than answered from general conversation history.
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


DOCUMENT_QUESTION_SYSTEM_PROMPT = (
    "You answer questions about documents using only the supplied "
    "document context. If a field contains a placeholder such as "
    "[Start Date], state that the actual value has not been provided "
    "and quote the placeholder. Never invent dates, names, amounts, "
    "or other missing values."
)


def _has_strong_hit(hits: list[dict]) -> bool:
    """Return whether any retrieved chunk passes the relevance threshold."""
    return any(
        h.get("distance", float("inf"))
        <= settings.relevance_distance_threshold
        for h in hits
    )


def _looks_like_document_question(message: str) -> bool:
    """
    Lightweight safeguard for common document questions.
    The supervisor remains useful, but should not be the only
    mechanism determining whether a question needs document context.
    """
    terms = (
        "document", "pdf", "file", "offer letter", "joining date",
        "probation", "salary", "ctc", "resume", "cv", "contract",
        "notice period", "mentioned in", "according to", "in the",
        "from the", "what does", "which date", "what date",
    )
    text = message.casefold()
    return any(term in text for term in terms)


def handle_turn(
    conversation_id: str,
    owner_id: str,
    message: str,
    document_id: str | None = None,
) -> dict:
    """
    Process a conversational turn.

    The caller must authenticate the owner and verify membership
    in the requested conversation before calling this function.
    """

    conversation_store.add_turn(
        conversation_id,
        "user",
        message,
    )

    resolved_query = resolve_query(
        conversation_id,
        message,
    )

    conversation_documents = vector_store.list_documents(
        owner_id=owner_id,
        conversation_id=conversation_id,
    )

    has_documents = bool(conversation_documents)

    # If the client supplies a document ID, verify that it belongs
    # to this authenticated owner and conversation before retrieval.
    if document_id:
        allowed_ids = {
            doc["document_id"] for doc in conversation_documents
        }
        if document_id not in allowed_ids:
            raise ValueError(
                "The requested document is not available in this conversation."
            )

    hits: list[dict] = []

    if has_documents:
        hits = retrieve(
            query=resolved_query,
            owner_id=owner_id,
            conversation_id=conversation_id,
            document_id=document_id,
        )

    llm_route = route_query(resolved_query)

    is_document_question = (
        document_id is not None
        or llm_route == "document_query"
        or _looks_like_document_question(message)
        or _looks_like_document_question(resolved_query)
        or _has_strong_hit(hits)
    )

    # A document question must not silently become general chat.
    if is_document_question:
        if not has_documents:
            reply = (
                "There are no indexed documents available in this "
                "conversation yet. Upload a document and try again."
            )
            sources = []
            verified = False
        elif not hits:
            reply = (
                "I couldn't find relevant information in the available "
                "documents. I can't confirm an answer from the documents."
            )
            sources = []
            verified = False
        else:
            rag_result = answer_from_hits(hits, resolved_query)
            reply = rag_result["answer"]
            sources = rag_result["sources"]

            verification = verify_answer(
                reply,
                rag_result["context"],
            )

            if not verification["verified"]:
                corrected = correct_answer(
                    reply,
                    rag_result["context"],
                    resolved_query,
                )

                corrected_verification = verify_answer(
                    corrected,
                    rag_result["context"],
                )

                if corrected_verification["verified"]:
                    reply = corrected
                    verification = corrected_verification

            verified = verification["verified"]

        conversation_store.add_turn(
            conversation_id,
            "assistant",
            reply,
        )

        return {
            "reply": reply,
            "agent_used": "rag_agent",
            "resolved_query": resolved_query,
            "sources": sources,
            "verified": verified,
        }

    # General chat is reserved for questions that don't need documents.
    history_text = conversation_store.as_text(
        conversation_id,
        limit=6,
    )

    prompt = (
        f"Conversation history:\n{history_text}\n\n"
        f"User: {message}"
    )

    reply = llm_gateway.generate(
        GENERAL_CHAT_SYSTEM_PROMPT,
        prompt,
    )

    conversation_store.add_turn(
        conversation_id,
        "assistant",
        reply,
    )

    return {
        "reply": reply,
        "agent_used": "conversation_agent",
        "resolved_query": resolved_query,
        "sources": [],
        "verified": None,
    }
