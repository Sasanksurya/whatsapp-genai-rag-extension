"""
Orchestrator — runs one full conversational turn through the agent
pipeline:

  Conversation Agent (resolve references)
        -> retrieve candidate chunks from the CURRENT conversation
        -> Supervisor Agent (route) + relevance override
        -> RAG pipeline OR general chat
        -> Verification Agent (only for RAG answers)

Conversation-aware security:

  Every document retrieval is restricted by BOTH:

      owner_id
      conversation_id

  This prevents a user who belongs to multiple conversations from
  retrieving documents from the wrong conversation.

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
    """
    Determine whether at least one retrieved chunk is strongly relevant
    to the user's question.

    ChromaDB uses cosine distance here, so a LOWER distance means
    greater similarity.
    """
    return any(
        h["distance"] <= settings.relevance_distance_threshold
        for h in hits
    )


def handle_turn(
    conversation_id: str,
    owner_id: str,
    message: str,
) -> dict:
    """
    Handle one complete conversational turn.

    Security:
    Document discovery and retrieval are restricted to the current
    conversation using:

        owner_id + conversation_id

    The caller is responsible for ensuring that the authenticated
    owner is authorized to access the conversation before this
    function is called.
    """

    conversation_store.add_turn(
        conversation_id,
        "user",
        message,
    )

    # ------------------------------------------------------------
    # 1. Resolve references such as:
    #
    #    "What skills does he have?"
    #
    # into a more explicit query using conversation context.
    # ------------------------------------------------------------
    resolved_query = resolve_query(
        conversation_id,
        message,
    )

    # ------------------------------------------------------------
    # 2. Check whether THIS conversation has indexed documents.
    #
    # IMPORTANT:
    # Do NOT check only owner_id.
    #
    # A user may belong to multiple conversations. We only want
    # documents associated with the current conversation.
    # ------------------------------------------------------------
    conversation_documents = vector_store.list_documents(
        owner_id=owner_id,
        conversation_id=conversation_id,
    )

    has_documents = bool(conversation_documents)

    # ------------------------------------------------------------
    # 3. Retrieve candidate chunks from THIS conversation.
    #
    # VectorStore enforces:
    #
    #     owner_id
    #     AND
    #     conversation_id
    #
    # so documents from another conversation cannot enter the
    # candidate set.
    # ------------------------------------------------------------
    hits: list[dict] = []

    if has_documents:
        hits = retrieve(
            query=resolved_query,
            owner_id=owner_id,
            conversation_id=conversation_id,
        )

    # ------------------------------------------------------------
    # 4. Ask Supervisor Agent to classify the request.
    # ------------------------------------------------------------
    llm_route = route_query(
        resolved_query
    )

    # ------------------------------------------------------------
    # 5. Decide whether to use RAG.
    #
    # RAG is selected when:
    #
    #   - the current conversation has documents AND
    #   - the supervisor classified it as document_query
    #
    # OR:
    #
    #   - there is a strongly relevant retrieved chunk.
    #
    # The relevance override prevents the supervisor from silently
    # sending an obvious document question to general chat.
    # ------------------------------------------------------------
    use_rag = (
        has_documents
        and (
            llm_route == "document_query"
            or _has_strong_hit(hits)
        )
    )

    # ------------------------------------------------------------
    # 6. RAG path
    # ------------------------------------------------------------
    if use_rag:
        rag_result = answer_from_hits(
            hits,
            resolved_query,
        )

        # --------------------------------------------------------
        # Verification Agent checks whether the generated answer
        # is actually grounded in the retrieved context.
        # --------------------------------------------------------
        verification = verify_answer(
            rag_result["answer"],
            rag_result["context"],
        )

        reply = rag_result["answer"]

        # --------------------------------------------------------
        # If verification fails, regenerate/re-ground the answer
        # using ONLY the retrieved context.
        # --------------------------------------------------------
        if not verification["verified"]:
            reply = correct_answer(
                reply,
                rag_result["context"],
                resolved_query,
            )

            # Verify the corrected answer again.
            verification = verify_answer(
                reply,
                rag_result["context"],
            )

            if (
                not verification["verified"]
                and verification["note"]
            ):
                reply += (
                    f"\n\n⚠️ Note: "
                    f"{verification['note']}"
                )

        conversation_store.add_turn(
            conversation_id,
            "assistant",
            reply,
        )

        return {
            "reply": reply,
            "agent_used": "rag_agent",
            "resolved_query": resolved_query,
            "sources": rag_result["sources"],
            "verified": verification["verified"],
        }

    # ------------------------------------------------------------
    # 7. General conversation path
    #
    # If the request is not routed to RAG, use recent conversation
    # history for a normal conversational response.
    # ------------------------------------------------------------
    history_text = conversation_store.as_text(
        conversation_id,
        limit=6,
    )

    prompt = (
        f"Conversation history:\n"
        f"{history_text}\n\n"
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