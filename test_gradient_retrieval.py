
from app.rag.pipeline import retrieve

OWNER_ID = "6aa067e36ad2785dc21ba5c5"
CONVERSATION_ID = "6aa0713b27d82bf8bdbd0a9e"
DOCUMENT_ID = "be69b05b-d8be-4451-8f11-5ecf4d306e41"

question = (
    "In Section 4.2, what is the mean-square convergence rate "
    "for strongly convex stochastic gradient descent?"
)

# Retrieve up to 20 chunks instead of the default 8.
hits = retrieve(
    query=question,
    owner_id=OWNER_ID,
    conversation_id=CONVERSATION_ID,
    document_id=DOCUMENT_ID,
    top_k=20,
)

print(f"\nRetrieved chunks: {len(hits)}")

for hit in hits:
    metadata = hit["metadata"]

    print("\n" + "=" * 60)
    print("Filename:", metadata.get("filename"))
    print("Chunk index:", metadata.get("chunk_index"))
    print("Distance:", hit.get("distance"))
    print("Text:")
    print(hit["text"])

print("\n--- CHECK FOR TARGET CHUNK ---")

target = [
    hit for hit in hits
    if hit["metadata"].get("chunk_index") == 43
]

if target:
    print("PASS: Chunk 43 was retrieved.")
    print(target[0]["text"])
else:
    print("FAIL: Chunk 43 was not retrieved.")
