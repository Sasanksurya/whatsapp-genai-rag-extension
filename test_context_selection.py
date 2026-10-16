
from app.rag.pipeline import retrieve, _build_context

QUERY = (
    "What contraction coefficient and generator inequality are "
    "established for the Stochastic Heavy Ball Lyapunov function?"
)

OWNER_ID = "6aa067e36ad2785dc21ba5c5"
CONVERSATION_ID = "6aa0713b27d82bf8bdbd0a9e"
DOCUMENT_ID = "dc5adec2-8b71-4acc-884b-e831059416b8"

MAX_CONTEXT_CHARS = 12000


def main():
    print("Running context-selection diagnostic...")

    hits = retrieve(
        query=QUERY,
        owner_id=OWNER_ID,
        conversation_id=CONVERSATION_ID,
        document_id=DOCUMENT_ID,
        top_k=35,
    )

    print(f"Retrieved chunks: {len(hits)}")

    if not hits:
        print("No chunks retrieved. Check the document ID and access scope.")
        return

    context = _build_context(
        hits=hits,
        query=QUERY,
        max_chars=MAX_CONTEXT_CHARS,
        owner_id=OWNER_ID,
        conversation_id=CONVERSATION_ID,
        document_id=DOCUMENT_ID,
    )

    print(f"Context characters: {len(context)}")
    print(f"Within 12000-character limit: {len(context) <= MAX_CONTEXT_CHARS}")
    print(f"Contains chunk 45: {'Chunk: 45]' in context}")
    print(f"Contains chunk 44: {'Chunk: 44]' in context}")

    print("\n--- Retrieved target chunk ---")
    for hit in hits:
        metadata = hit.get("metadata") or {}
        if metadata.get("chunk_index") == 45:
            print("Chunk 45 was retrieved.")
            print((hit.get("text") or "")[:1200])
            break
    else:
        print("Chunk 45 was not in the retrieved results.")

    print("\n--- Chunks included in final context ---")
    import re

    included = re.findall(r"\[Source: .*? \| Chunk: (.*?)\]", context)
    print(included)

    print("\n--- Context preview ---")
    print(context[:2500])


if __name__ == "__main__":
    main()
 