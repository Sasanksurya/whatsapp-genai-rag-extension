"""

Advanced retrieval helpers for hybrid RAG.



This module does not access the database. Owner, conversation, and document

filtering must be applied by VectorStore before these helpers are called.

"""



import logging

import os

import re

from functools import lru_cache



import numpy as np

from dotenv import load_dotenv

from rank_bm25 import BM25Okapi



load_dotenv()

logger = logging.getLogger(__name__)





# ---------------------------------------------------------------------

# Configuration

# ---------------------------------------------------------------------



def _env_bool(name: str, default: bool) -> bool:

    value = os.getenv(name, str(default)).strip().lower()

    return value in {"1", "true", "yes", "on"}





def _env_int(name: str, default: int) -> int:

    try:

        return int(os.getenv(name, str(default)))

    except (TypeError, ValueError):

        return default





def _env_float(name: str, default: float) -> float:

    try:

        return float(os.getenv(name, str(default)))

    except (TypeError, ValueError):

        return default





RETRIEVAL_MODE = os.getenv("RETRIEVAL_MODE", "hybrid").strip().lower()

DENSE_CANDIDATES = max(1, _env_int("RETRIEVAL_DENSE_CANDIDATES", 50))

SPARSE_CANDIDATES = max(1, _env_int("RETRIEVAL_SPARSE_CANDIDATES", 50))

RRF_K = max(1, _env_int("RETRIEVAL_RRF_K", 60))

RERANK_ENABLED = _env_bool("RETRIEVAL_RERANK_ENABLED", True)



RERANK_MODEL = os.getenv(

    "RETRIEVAL_RERANK_MODEL",

    "cross-encoder/ms-marco-MiniLM-L-6-v2",

)



RERANK_POOL = max(1, _env_int("RETRIEVAL_RERANK_POOL", 50))



# MMR can be controlled in .env using RETRIEVAL_MMR_ENABLED=true/false.

MMR_ENABLED = _env_bool("RETRIEVAL_MMR_ENABLED", True)

MMR_LAMBDA = min(

    1.0,

    max(0.0, _env_float("RETRIEVAL_MMR_LAMBDA", 0.7)),

)



HYBRID_MAX_CORPUS = max(

    1,

    _env_int("RETRIEVAL_HYBRID_MAX_CORPUS", 5000),

)





# ---------------------------------------------------------------------

# General helpers

# ---------------------------------------------------------------------



def tokenize(text: str) -> list[str]:

    """Lowercase alphanumeric tokenization; retain useful numbers and IDs."""

    return re.findall(r"[a-z0-9]+", str(text).lower())





def normalize_rows(matrix: np.ndarray) -> np.ndarray:

    """L2-normalize matrix rows safely."""

    matrix = np.asarray(matrix, dtype=np.float32)



    if matrix.ndim != 2:

        raise ValueError("Expected a two-dimensional matrix.")



    if not np.all(np.isfinite(matrix)):

        raise ValueError("Embedding matrix contains non-finite values.")



    norms = np.linalg.norm(matrix, axis=1, keepdims=True)

    norms = np.maximum(norms, 1e-12)



    return matrix / norms





def min_max(values) -> np.ndarray:

    """Normalize finite scores to [0, 1]."""

    arr = np.asarray(values, dtype=np.float32)



    if arr.size == 0:

        return arr



    if not np.all(np.isfinite(arr)):

        raise ValueError("Score array contains non-finite values.")



    lo = float(arr.min())

    hi = float(arr.max())



    if hi - lo < 1e-9:

        return np.ones_like(arr)



    return (arr - lo) / (hi - lo)





# ---------------------------------------------------------------------

# Dense ranking

# ---------------------------------------------------------------------



def dense_rank(similarities: np.ndarray, top_n: int) -> list[int]:

    """Return indices of the top_n highest similarity scores."""

    if top_n <= 0:

        return []



    scores = np.asarray(similarities, dtype=np.float64).reshape(-1)

    valid_indices = np.flatnonzero(np.isfinite(scores))



    if valid_indices.size == 0:

        return []



    order = np.argsort(-scores[valid_indices], kind="stable")



    return valid_indices[order[:top_n]].astype(int).tolist()





# ---------------------------------------------------------------------

# Sparse ranking: BM25 with query expansion

# ---------------------------------------------------------------------



def _expand_query_tokens(query: str) -> list[str]:

    """

    Expand technical queries with relevant terminology.



    Original tokens are preserved. Synonyms are added only when the

    corresponding phrase occurs in the normalized query.

    """

    tokens = tokenize(query)

    query_text = " ".join(tokens)



    expansions = {

        "generator inequality": [

            "estimate",

            "drift",

            "lyapunov",

            "lambda",

            "mu",

            "sigma",

            "alpha",

        ],

        "lower bound": [

            "completing",

            "square",

            "strong",

            "convexity",

            "norm",

            "mu",

        ],

        "completed square": [

            "completing",

            "square",

            "strong",

            "convexity",

            "norm",

        ],

        "contraction coefficient": [
            "contraction",
            "lambda",
            "hb",
            "generator",
            "estimate",
            "mu",
            "sigma",
            "alpha",
            "rate",
            "decay",
            "dissipation",
            "drift",
            "lyapunov",
            "stochastic",
        ],
        "heavy ball": [
            "hb",
            "lyapunov",
            "generator",
            "estimate",
            "stochastic",
            "contraction",
            "lambda",
            "decay",
            "rate",
        ],

        "strongly convex sgd": [

            "gradient",

            "noise",

            "step",

            "size",

            "lyapunov",

        ],

    }



    expanded = list(tokens)



    for phrase, extra_terms in expansions.items():

        if phrase in query_text:

            expanded.extend(extra_terms)



    # Remove duplicate tokens without changing their original order.

    return list(dict.fromkeys(expanded))





def sparse_rank(query: str, docs: list[str], top_n: int) -> list[int]:

    """

    Return BM25-ranked document indices using expanded query tokens.



    Returns only indices with positive, finite BM25 scores.

    """

    if top_n <= 0 or not docs:

        return []



    query_tokens = _expand_query_tokens(query)



    if not query_tokens:

        return []



    tokenized_docs = [tokenize(doc or "") for doc in docs]



    if not any(tokenized_docs):

        return []



    bm25 = BM25Okapi(tokenized_docs)



    scores = np.asarray(

        bm25.get_scores(query_tokens),

        dtype=np.float64,

    )



    if scores.size == 0:

        return []



    valid_indices = np.flatnonzero(

        np.isfinite(scores) & (scores > 0)

    )



    if valid_indices.size == 0:

        return []



    order = np.argsort(-scores[valid_indices], kind="stable")



    return valid_indices[order[:top_n]].astype(int).tolist()





# ---------------------------------------------------------------------

# Reciprocal Rank Fusion

# ---------------------------------------------------------------------



def rrf_fuse(

    rankings: list[list[int]],

    k: int = RRF_K,

) -> list[tuple[int, float]]:

    """Fuse ranked lists using Reciprocal Rank Fusion."""

    k = max(1, int(k))

    scores: dict[int, float] = {}



    for ranking in rankings:

        seen: set[int] = set()



        for rank, raw_idx in enumerate(ranking, start=1):

            idx = int(raw_idx)



            if idx in seen:

                continue



            seen.add(idx)

            scores[idx] = scores.get(idx, 0.0) + 1.0 / (k + rank)



    return sorted(

        scores.items(),

        key=lambda item: (-item[1], item[0]),

    )





# ---------------------------------------------------------------------

# Cross-encoder reranking

# ---------------------------------------------------------------------



@lru_cache(maxsize=1)

def _load_reranker():

    """Load and cache the cross-encoder model; return None if unavailable."""

    try:

        from sentence_transformers import CrossEncoder



        logger.info(

            "Loading cross-encoder reranker: %s",

            RERANK_MODEL,

        )



        return CrossEncoder(RERANK_MODEL)



    except Exception as exc:

        logger.warning(

            "Reranker unavailable; using fused ranking: %s",

            exc,

        )



        return None





def rerank_scores(

    query: str,

    texts: list[str],

) -> list[float] | None:

    """Return one cross-encoder score per text, or None on failure/disabled."""

    if not RERANK_ENABLED or not texts:

        return None



    model = _load_reranker()



    if model is None:

        return None



    try:

        pairs = [(query, text or "") for text in texts]



        scores = np.asarray(

            model.predict(pairs),

            dtype=np.float64,

        ).reshape(-1)



        if len(scores) != len(texts):

            logger.warning(

                "Reranker returned %d scores for %d texts.",

                len(scores),

                len(texts),

            )

            return None



        if not np.all(np.isfinite(scores)):

            logger.warning(

                "Reranker returned non-finite scores."

            )

            return None



        return scores.tolist()



    except Exception as exc:

        logger.warning(

            "Reranking failed; using fused ranking: %s",

            exc,

        )



        return None





# ---------------------------------------------------------------------

# Maximal Marginal Relevance

# ---------------------------------------------------------------------



def mmr_select(

    relevance: np.ndarray,

    embeddings: np.ndarray,

    k: int,

    lambda_: float = MMR_LAMBDA,

) -> list[int]:

    """

    Select relevant and diverse candidates using MMR.



    Returns indices into the input relevance array.

    """

    relevance = np.asarray(

        relevance,

        dtype=np.float64,

    ).reshape(-1)



    embeddings = np.asarray(

        embeddings,

        dtype=np.float32,

    )



    if k <= 0 or relevance.size == 0:

        return []



    if embeddings.ndim != 2:

        raise ValueError(

            "MMR embeddings must be a two-dimensional matrix."

        )



    if embeddings.shape[0] != relevance.size:

        raise ValueError(

            "Embedding rows must match relevance score count."

        )



    if not np.all(np.isfinite(relevance)):

        raise ValueError(

            "MMR relevance scores contain non-finite values."

        )



    embeddings = normalize_rows(embeddings)



    lambda_ = min(1.0, max(0.0, float(lambda_)))

    k = min(int(k), relevance.size)



    selected: list[int] = []

    remaining = list(range(relevance.size))



    while remaining and len(selected) < k:

        best_idx = None

        best_score = -np.inf



        for idx in remaining:

            if selected:

                redundancy = float(

                    np.max(

                        embeddings[idx] @ embeddings[selected].T

                    )

                )

            else:

                redundancy = 0.0



            score = (

                lambda_ * float(relevance[idx])

                - (1.0 - lambda_) * redundancy

            )



            # Stable tie-breaking: retain the first candidate.

            if score > best_score:

                best_idx = idx

                best_score = score



        if best_idx is None:

            break



        selected.append(best_idx)

        remaining.remove(best_idx)



    return selected
