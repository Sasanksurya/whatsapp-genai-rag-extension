"""
Vector store — ChromaDB (embedded, local, free) with sentence-transformers
embeddings (local, free — no embedding API cost).

Security note (see project Phase 5): `owner_id` is stored as metadata
on every chunk and MUST be passed as a filter on every query. This is
what stops User B from retrieving User A's documents just because
they guess a query that matches — the filter is enforced here, not
left to the LLM to "decide" who owns what.
"""
import uuid

import chromadb
from sentence_transformers import SentenceTransformer

from app.core.config import settings

_embedder: SentenceTransformer | None = None


def get_embedder() -> SentenceTransformer:
    global _embedder
    if _embedder is None:
        _embedder = SentenceTransformer(settings.embedding_model_name)
    return _embedder


class VectorStore:
    def __init__(self) -> None:
        self._client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
        self._collection = self._client.get_or_create_collection(
            name="documents",
            metadata={"hnsw:space": "cosine"},
        )

    def add_document_chunks(
        self,
        chunks: list[str],
        owner_id: str,
        document_id: str,
        filename: str,
        source_type: str = "upload",
    ) -> int:
        embedder = get_embedder()
        embeddings = embedder.encode(chunks).tolist()
        ids = [f"{document_id}:{i}" for i in range(len(chunks))]
        metadatas = [
            {
                "owner_id": owner_id,
                "document_id": document_id,
                "filename": filename,
                "chunk_index": i,
                "source_type": source_type,  # "upload" | "web" | "drive"
            }
            for i in range(len(chunks))
        ]
        self._collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=chunks,
            metadatas=metadatas,
        )
        return len(chunks)

    def query(self, query_text: str, owner_id: str, top_k: int | None = None) -> list[dict]:
        top_k = top_k or settings.retrieval_top_k
        embedder = get_embedder()
        query_embedding = embedder.encode([query_text]).tolist()

        results = self._collection.query(
            query_embeddings=query_embedding,
            n_results=top_k,
            where={"owner_id": owner_id},  # <-- authorization filter, enforced here
        )

        hits = []
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]
        for doc, meta, dist in zip(docs, metas, distances):
            hits.append({"text": doc, "metadata": meta, "distance": dist})
        return hits

    def list_documents(self, owner_id: str) -> list[dict]:
        results = self._collection.get(where={"owner_id": owner_id})
        seen = {}
        for meta in results.get("metadatas", []):
            doc_id = meta["document_id"]
            if doc_id not in seen:
                seen[doc_id] = {"document_id": doc_id, "filename": meta["filename"]}
        return list(seen.values())


def new_document_id() -> str:
    return str(uuid.uuid4())


vector_store = VectorStore()
