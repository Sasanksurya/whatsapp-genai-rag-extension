"""

Vector store — ChromaDB with local sentence-transformers embeddings.

Every chunk is stored with owner_id and conversation_id. Every query filters

by both values before ranking. An optional document_id narrows retrieval to a

single uploaded document.

Retrieval:

- query(): dense-only ChromaDB ANN retrieval

- hybrid_query(): dense + BM25 -> weighted RRF -> cross-encoder rerank -> optional MMR

Debugging:

- Set RETRIEVAL_DEBUG=true to log candidate-stage diagnostics.

- Set RETRIEVAL_DEBUG_CHUNKS=41,45 to inspect selected chunk indices.

- Set RETRIEVAL_DEBUG_RERANK_TOP_N=10 to log the top N reranked candidates

  with scores and text previews.

"""

import logging

import os

import uuid

import chromadb

import numpy as np

from sentence_transformers import SentenceTransformer

from app.core.config import settings

from app.rag.retrieval import (

    DENSE_CANDIDATES,

    HYBRID_MAX_CORPUS,

    MMR_ENABLED,

    RERANK_POOL,

    RRF_K,

    SPARSE_CANDIDATES,

    dense_rank,

    mmr_select,

    normalize_rows,

    rerank_scores,

    sparse_rank,

)

logger = logging.getLogger(__name__)

logger.setLevel(logging.INFO)

def _env_float(name: str, default: float) -> float:

    """Read a finite, non-negative floating-point environment setting."""

    try:

        value = float(os.getenv(name, str(default)))

    except (TypeError, ValueError):

        return default

    if not np.isfinite(value) or value < 0:

        return default

    return value

# Weighted reciprocal-rank fusion settings.

# Defaults give BM25 twice the contribution of dense retrieval; tune via .env.

DENSE_RRF_WEIGHT = _env_float("RETRIEVAL_DENSE_RRF_WEIGHT", 1.0)

SPARSE_RRF_WEIGHT = _env_float("RETRIEVAL_SPARSE_RRF_WEIGHT", 2.0)

def _weighted_rrf_fuse(

    rankings: list[list[int]],

    weights: list[float],

    k: int = RRF_K,

) -> list[tuple[int, float]]:

    """Fuse ranked lists using configurable weighted Reciprocal Rank Fusion."""

    if len(rankings) != len(weights):

        raise ValueError("Each ranking must have exactly one fusion weight.")

    k = max(1, int(k))

    scores: dict[int, float] = {}

    for ranking, weight in zip(rankings, weights):

        weight = float(weight)

        if not np.isfinite(weight) or weight < 0:

            raise ValueError("RRF weights must be finite and non-negative.")

        if weight == 0:

            continue

        seen: set[int] = set()

        for rank, raw_idx in enumerate(ranking, start=1):

            idx = int(raw_idx)

            if idx in seen:

                continue

            seen.add(idx)

            scores[idx] = scores.get(idx, 0.0) + weight / (k + rank)

    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))

_embedder: SentenceTransformer | None = None

def get_embedder() -> SentenceTransformer:

    """Load the embedding model once per process."""

    global _embedder

    if _embedder is None:

        _embedder = SentenceTransformer(settings.embedding_model_name)

    return _embedder

def _build_where(

    owner_id: str,

    conversation_id: str,

    document_id: str | None = None,

) -> dict:

    """Build the mandatory access-control filter for ChromaDB."""

    conditions = [

        {"owner_id": owner_id},

        {"conversation_id": conversation_id},

    ]

    if document_id:

        conditions.append({"document_id": document_id})

    return {"$and": conditions}

def _debug_enabled() -> bool:

    """Return whether retrieval diagnostics are enabled."""

    return os.getenv("RETRIEVAL_DEBUG", "false").strip().lower() in {

        "1",

        "true",

        "yes",

        "on",

    }

def _debug_chunk_ids() -> set[str]:

    """Read comma-separated chunk indices to inspect."""

    raw = os.getenv("RETRIEVAL_DEBUG_CHUNKS", "41,45")

    return {part.strip() for part in raw.split(",") if part.strip()}

def _debug_rerank_top_n() -> int:

    """Number of reranked candidates to include in diagnostic logs."""

    raw = os.getenv("RETRIEVAL_DEBUG_RERANK_TOP_N", "10")

    try:

        return max(0, min(100, int(raw)))

    except (TypeError, ValueError):

        return 10

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

        conversation_id: str,

        document_id: str,

        filename: str,

        source_type: str = "upload",

    ) -> int:

        """Embed and store chunks with ownership and document metadata."""

        if not chunks:

            return 0

        embeddings = get_embedder().encode(chunks).tolist()

        ids = [f"{document_id}:{i}" for i in range(len(chunks))]

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

        # upsert makes re-indexing the same document IDs safe to retry.

        self._collection.upsert(

            ids=ids,

            embeddings=embeddings,

            documents=chunks,

            metadatas=metadatas,

        )

        return len(chunks)

    def get_neighboring_chunks(
        self,
        chunk_indices: list[int],
        owner_id: str,
        conversation_id: str,
        document_id: str,
        window: int = 1,
    ) -> list[dict]:
        """Fetch nearby chunks from one authorized document."""
        if not chunk_indices or window < 0:
            return []

        target_indices = set()
        for index in chunk_indices:
            if isinstance(index, int):
                target_indices.update(
                    range(max(0, index - window), index + window + 1)
                )

        if not target_indices:
            return []

        results = self._collection.get(
            where=_build_where(
                owner_id=owner_id,
                conversation_id=conversation_id,
                document_id=document_id,
            ),
            include=["documents", "metadatas"],
        )

        docs = results.get("documents") or []
        metadatas = results.get("metadatas") or []
        neighbors = []

        for text, metadata in zip(docs, metadatas):
            if not metadata:
                continue
            index = metadata.get("chunk_index")
            if index in target_indices:
                neighbors.append({"text": text, "metadata": metadata})

        neighbors.sort(
            key=lambda hit: hit.get("metadata", {}).get("chunk_index", -1)
        )
        return neighbors

    def query(

        self,

        query_text: str,

        owner_id: str,

        conversation_id: str,

        document_id: str | None = None,

        top_k: int | None = None,

    ) -> list[dict]:

        """Dense-only retrieval, always restricted to authorized chunks."""

        top_k = settings.retrieval_top_k if top_k is None else max(1, int(top_k))

        query_embedding = get_embedder().encode([query_text]).tolist()

        results = self._collection.query(

            query_embeddings=query_embedding,

            n_results=top_k,

            where=_build_where(owner_id, conversation_id, document_id),

            include=["documents", "metadatas", "distances"],

        )

        docs = (results.get("documents") or [[]])[0]

        metas = (results.get("metadatas") or [[]])[0]

        distances = (results.get("distances") or [[]])[0]

        return [

            {"text": doc, "metadata": meta, "distance": float(dist)}

            for doc, meta, dist in zip(docs, metas, distances)

        ]

    def hybrid_query(

        self,

        query_text: str,

        owner_id: str,

        conversation_id: str,

        document_id: str | None = None,

        top_k: int | None = None,

    ) -> list[dict]:

        """Retrieve authorized chunks using dense, sparse, fusion, reranking and MMR."""

        top_k = settings.retrieval_top_k if top_k is None else max(1, int(top_k))

        where = _build_where(owner_id, conversation_id, document_id)

        # Access-control filtering occurs before any retrieval/ranking operation.

        corpus = self._collection.get(

            where=where,

            include=["documents", "metadatas", "embeddings"],

        )

        ids = corpus.get("ids") or []

        docs = corpus.get("documents") or []

        metas = corpus.get("metadatas") or []

        raw_embeddings = corpus.get("embeddings")

        n = len(ids)

        if n == 0:

            logger.info("hybrid_query: authorized corpus is empty")

            return []

        if len(docs) != n or len(metas) != n:

            raise RuntimeError(

                "ChromaDB returned inconsistent IDs, documents, or metadata lengths."

            )

        # For very large corpora, avoid loading/ranking the entire corpus in memory.

        if n > HYBRID_MAX_CORPUS:

            logger.info(

                "Corpus (%d chunks) exceeds HYBRID_MAX_CORPUS=%d; using dense ANN.",

                n,

                HYBRID_MAX_CORPUS,

            )

            return self.query(

                query_text=query_text,

                owner_id=owner_id,

                conversation_id=conversation_id,

                document_id=document_id,

                top_k=top_k,

            )

        if raw_embeddings is None:

            raise RuntimeError("ChromaDB did not return embeddings for hybrid retrieval.")

        matrix = normalize_rows(np.asarray(raw_embeddings, dtype=np.float32))

        if matrix.shape[0] != n:

            raise RuntimeError("Embedding count does not match the document count.")

        q_vec = np.asarray(

            get_embedder().encode([query_text])[0],

            dtype=np.float32,

        )

        q_norm = float(np.linalg.norm(q_vec))

        if not np.isfinite(q_norm) or q_norm <= 1e-12:

            raise ValueError("Query embedding is invalid or has zero magnitude.")

        q_vec /= q_norm

        similarities = matrix @ q_vec

        dense_ranked = dense_rank(similarities, min(n, DENSE_CANDIDATES))

        sparse_ranked = sparse_rank(query_text, docs, min(n, SPARSE_CANDIDATES))

        fused_all = _weighted_rrf_fuse(

            [dense_ranked, sparse_ranked],

            weights=[DENSE_RRF_WEIGHT, SPARSE_RRF_WEIGHT],

        )

        if not fused_all:

            logger.warning("hybrid_query: no candidates for query=%r", query_text[:150])

            return []

        # Keep enough candidates for top_k, even if RERANK_POOL is configured lower.

        pool_limit = min(len(fused_all), max(int(RERANK_POOL), top_k))

        fused_pool = fused_all[:pool_limit]

        pool_indices = [idx for idx, _score in fused_pool]

        cross_encoder_scores = rerank_scores(

            query_text,

            [docs[i] for i in pool_indices],

        )

        dense_position = {

            idx: rank for rank, idx in enumerate(dense_ranked, start=1)

        }

        sparse_position = {

            idx: rank for rank, idx in enumerate(sparse_ranked, start=1)

        }

        fused_position = {

            idx: rank for rank, (idx, _score) in enumerate(fused_all, start=1)

        }

        if (

            cross_encoder_scores is not None

            and len(cross_encoder_scores) == len(pool_indices)

        ):

            cross_encoder_by_index = dict(zip(pool_indices, cross_encoder_scores))

            rerank_order = np.argsort(

                -np.asarray(cross_encoder_scores, dtype=np.float64),

                kind="stable",

            )

            rerank_position = {

                pool_indices[int(pos)]: rank

                for rank, pos in enumerate(rerank_order, start=1)

            }

            reranked = True

            # Diagnostic-only: show the highest-scoring candidates and text previews.

            # This does not change candidate selection or ranking.

            if _debug_enabled():

                debug_top_n = _debug_rerank_top_n()

                if debug_top_n:

                    top_positions = rerank_order[:debug_top_n]

                    logger.warning(

                        "RERANK_TOP%d query=%r candidates=%s",

                        debug_top_n,

                        query_text[:120],

                        [

                            {

                                "chunk_index": metas[pool_indices[int(pos)]].get(

                                    "chunk_index"

                                ),

                                "score": round(

                                    float(cross_encoder_scores[int(pos)]), 4

                                ),

                                "text": docs[pool_indices[int(pos)]][:300],

                            }

                            for pos in top_positions

                        ],

                    )

        else:

            cross_encoder_by_index = {}

            rerank_position = {}

            reranked = False

        # Preserve fused scores for diagnostics and optional MMR relevance.
        rrf_by_index = dict(fused_all)

        if reranked:
            # Keep the hybrid top-k candidate set intact, then use the
            # cross-encoder and hybrid ranks to order those candidates.
            # This prevents reranking from dropping a candidate that hybrid
            # retrieval already placed inside the requested top-k.
            rerank_ranked_indices = [
                pool_indices[int(pos)] for pos in rerank_order
            ]

            fused_rank_by_index = {
                idx: rank
                for rank, (idx, _score) in enumerate(fused_all, start=1)
            }
            rerank_rank_by_index = {
                idx: rank
                for rank, idx in enumerate(rerank_ranked_indices, start=1)
            }

            def combined_rank_score(idx: int) -> float:
                score = 0.0
                fused_rank = fused_rank_by_index.get(idx)
                rerank_rank = rerank_rank_by_index.get(idx)

                if fused_rank is not None:
                    score += 1.0 / (60 + fused_rank)
                if rerank_rank is not None:
                    score += 1.0 / (60 + rerank_rank)

                return score

            # Preserve the hybrid top-k membership. The cross-encoder changes
            # order within this set, but cannot remove a hybrid top-k result.
            hybrid_shortlist = [
                idx for idx, _score in fused_all[:min(top_k, len(fused_all))]
            ]
            selected_indices = sorted(
                hybrid_shortlist,
                key=combined_rank_score,
                reverse=True,
            )

            # Diagnostic for the requested target chunk and final cutoff.
            if _debug_enabled() and "43" in _debug_chunk_ids():
                combined_ranked = sorted(
                    hybrid_shortlist,
                    key=combined_rank_score,
                    reverse=True,
                )
                target_index = next(
                    (
                        idx for idx in fused_rank_by_index
                        if str(metas[idx].get("chunk_index", "")) == "43"
                    ),
                    None,
                )
                target_selected = target_index in selected_indices if target_index is not None else False
                cutoff_score = (
                    combined_rank_score(combined_ranked[-1])
                    if combined_ranked else None
                )

                logger.warning(
                    "COMBINED_RANK_DIAGNOSTIC target_index=%s "
                    "target_fused_rank=%s target_rerank_rank=%s "
                    "target_score=%s cutoff_score=%s top_k=%s "
                    "target_selected=%s selection_policy=hybrid_top_k_protected",
                    target_index,
                    fused_rank_by_index.get(target_index)
                    if target_index is not None else None,
                    rerank_rank_by_index.get(target_index)
                    if target_index is not None else None,
                    combined_rank_score(target_index)
                    if target_index is not None else None,
                    cutoff_score,
                    top_k,
                    target_selected,
                )

                logger.warning(
                    "COMBINED_RANK_TOP20 %s",
                    [
                        {
                            "chunk_index": metas[idx].get("chunk_index"),
                            "fused_rank": fused_rank_by_index.get(idx),
                            "rerank_rank": rerank_rank_by_index.get(idx),
                            "score": round(combined_rank_score(idx), 6),
                        }
                        for idx in combined_ranked
                    ],
                )
        else:
            shortlist = fused_all[:min(top_k, len(fused_all))]
            selected_indices = [idx for idx, _score in shortlist]

        # MMR operates on the selected shortlist. When disabled, preserve the

        # RRF order or cross-encoder order, depending on whether reranking ran.

        if MMR_ENABLED and len(selected_indices) > 1:

            shortlist_relevance = np.asarray(

                [rrf_by_index[idx] for idx in selected_indices],

                dtype=np.float32,

            )

            chosen_positions = mmr_select(

                relevance=shortlist_relevance,

                embeddings=matrix[selected_indices],

                k=min(top_k, len(selected_indices)),

            )

            final_indices = [selected_indices[pos] for pos in chosen_positions]

        else:

            final_indices = selected_indices

        # Optional per-chunk diagnostics. Access filtering is already applied:

        # metas contains only chunks authorized by owner/conversation/document.

        if _debug_enabled():

            target_chunk_ids = _debug_chunk_ids()

            found_targets: set[str] = set()

            for corpus_index, meta in enumerate(metas):

                chunk_id = str(meta.get("chunk_index", ""))

                if chunk_id not in target_chunk_ids:

                    continue

                found_targets.add(chunk_id)

                logger.warning(

                    "RETRIEVAL_DIAGNOSTIC query=%r chunk_index=%s "

                    "dense=%s sparse=%s fused=%s rerank_pool=%s "

                    "final_selected=%s mmr_enabled=%s reranked=%s "

                    "dense_rank=%s sparse_rank=%s fused_rank=%s rerank_rank=%s",

                    query_text[:120],

                    chunk_id,

                    corpus_index in dense_ranked,

                    corpus_index in sparse_ranked,

                    corpus_index in fused_position,

                    corpus_index in pool_indices,

                    corpus_index in final_indices,

                    MMR_ENABLED,

                    reranked,

                    dense_position.get(corpus_index),

                    sparse_position.get(corpus_index),

                    fused_position.get(corpus_index),

                    rerank_position.get(corpus_index),

                )

            # Distinguish a chunk absent from this filtered corpus from one that

            # exists but was not retrieved into candidate sets.

            for missing_id in sorted(target_chunk_ids - found_targets):

                logger.warning(

                    "RETRIEVAL_DIAGNOSTIC query=%r chunk_index=%s "

                    "not_found_in_authorized_corpus=true",

                    query_text[:120],

                    missing_id,

                )

        logger.info(

            "hybrid_query corpus=%d dense=%d sparse=%d fused=%d pool=%d "

            "reranked=%s selected=%d",

            n,

            len(dense_ranked),

            len(sparse_ranked),

            len(fused_all),

            len(pool_indices),

            reranked,

            len(final_indices),

        )

        hits = []

        for corpus_index in final_indices:

            hits.append(

                {

                    "text": docs[corpus_index],

                    "metadata": metas[corpus_index],

                    "distance": float(1.0 - similarities[corpus_index]),

                    "scores": {

                        "rrf": float(rrf_by_index[corpus_index]),

                        "rerank": cross_encoder_by_index.get(corpus_index),

                        "relevance": float(rrf_by_index[corpus_index]),

                    },

                }

            )

        return hits

    def list_documents(

        self,

        owner_id: str,

        conversation_id: str | None = None,

    ) -> list[dict]:

        """List unique documents belonging to the specified owner/conversation."""

        if conversation_id:

            where = {

                "$and": [

                    {"owner_id": owner_id},

                    {"conversation_id": conversation_id},

                ]

            }

        else:

            where = {"owner_id": owner_id}

        results = self._collection.get(where=where, include=["metadatas"])

        seen: dict[str, dict] = {}

        for meta in results.get("metadatas") or []:

            if not meta:

                continue

            doc_id = meta.get("document_id")

            if doc_id and doc_id not in seen:

                seen[doc_id] = {

                    "document_id": doc_id,

                    "filename": meta.get("filename", ""),

                }

        return list(seen.values())

    def delete_document(self, document_id: str) -> None:

        """Delete all chunks belonging to one document."""

        self._collection.delete(where={"document_id": document_id})

def new_document_id() -> str:

    """Generate a unique document ID."""

    return str(uuid.uuid4())

vector_store = VectorStore()
