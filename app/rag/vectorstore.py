"""
Vector store — ChromaDB (embedded, local, free) with sentence-transformers
embeddings (local, free — no embedding API cost).

Security:
Every document chunk is stored with both:
    - owner_id
    - conversation_id

Every conversation-aware query MUST filter by both values.

This prevents:
    1. User A from retrieving User B's documents.
    2. User A from retrieving documents belonging to another
       conversation that User A participates in.
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
        self._client = chromadb.PersistentClient(
            path=settings.chroma_persist_dir
        )

        self._collection = self._client.get_or_create_collection(
            name="documents",
            metadata={"hnsw:space": "cosine"},
        )

    def add_document_chunks(
        self,
        chunks: list[str],
        owner_id: str,
        conversation_id: str,
        document_id: str,
        filename: str,
        source_type: str = "upload",
    ) -> int:
        """
        Store document chunks with ownership and conversation metadata.

        owner_id:
            Authenticated user who uploaded the document.

        conversation_id:
            Conversation where the document was uploaded/shared.

        Both values are later used as mandatory retrieval filters.
        """

        embedder = get_embedder()
        embeddings = embedder.encode(chunks).tolist()

        ids = [
            f"{document_id}:{i}"
            for i in range(len(chunks))
        ]

        metadatas = [
            {
                "owner_id": owner_id,
                "conversation_id": conversation_id,
                "document_id": document_id,
                "filename": filename,
                "chunk_index": i,
                "source_type": source_type,
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

    def query(
        self,
        query_text: str,
        owner_id: str,
        conversation_id: str,
        top_k: int | None = None,
    ) -> list[dict]:
        """
        Retrieve only chunks belonging to the authenticated user AND
        the requested conversation.

        This is the final authorization boundary for RAG retrieval.
        """

        top_k = top_k or settings.retrieval_top_k

        embedder = get_embedder()

        query_embedding = embedder.encode(
            [query_text]
        ).tolist()

        results = self._collection.query(
            query_embeddings=query_embedding,
            n_results=top_k,
            where={
                "$and": [
                    {"owner_id": owner_id},
                    {"conversation_id": conversation_id},
                ]
            },
        )

        hits = []

        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        for doc, meta, dist in zip(docs, metas, distances):
            hits.append(
                {
                    "text": doc,
                    "metadata": meta,
                    "distance": dist,
                }
            )

        return hits

    def list_documents(
        self,
        owner_id: str,
        conversation_id: str | None = None,
    ) -> list[dict]:
        """
        List documents belonging to the authenticated owner.

        If conversation_id is provided, only documents belonging to
        that conversation are returned.
        """

        if conversation_id:
            where = {
                "$and": [
                    {"owner_id": owner_id},
                    {"conversation_id": conversation_id},
                ]
            }
        else:
            where = {
                "owner_id": owner_id,
            }

        results = self._collection.get(
            where=where
        )

        seen = {}

        for meta in results.get("metadatas", []):
            doc_id = meta["document_id"]

            if doc_id not in seen:
                seen[doc_id] = {
                    "document_id": doc_id,
                    "filename": meta["filename"],
                }

        return list(seen.values())


def new_document_id() -> str:
    return str(uuid.uuid4())


vector_store = VectorStore()