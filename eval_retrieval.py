
"""
Retrieval evaluation harness (read-only).

Example:
    python -u .\\eval_retrieval.py .\\eval_set.json --k 20 --label hybrid_rerank --out .\\eval_results.jsonl
"""

import argparse
import json
import math
import statistics
import time

from app.rag.pipeline import retrieve

CUTOFFS = (1, 3, 5, 10, 20)


def _dcg(rels):
    """Calculate discounted cumulative gain."""
    return sum(r / math.log2(i + 2) for i, r in enumerate(rels))


def _score_query(got, relevant, k):
    """Calculate retrieval metrics for a single query."""
    row = {}

    for c in CUTOFFS:
        if c > k:
            continue

        top = got[:c]
        found = relevant.intersection(top)

        row[f"recall@{c}"] = len(found) / len(relevant)
        row[f"hit@{c}"] = 1.0 if found else 0.0

        rels = [1 if g in relevant else 0 for g in top]
        ideal = [1] * min(len(relevant), c)

        row[f"ndcg@{c}"] = _dcg(rels) / _dcg(ideal)

    row["mrr"] = next(
        (
            1.0 / rank
            for rank, chunk_id in enumerate(got, start=1)
            if chunk_id in relevant
        ),
        0.0,
    )

    return row


def _run(item, k):
    """Run retrieval and measure latency."""
    t0 = time.perf_counter()

    hits = retrieve(
        query=item["query"],
        owner_id=item["owner_id"],
        conversation_id=item["conversation_id"],
        document_id=item["document_id"],
        top_k=k,
    )

    return hits, time.perf_counter() - t0


def main():
    ap = argparse.ArgumentParser(
        description="Evaluate retrieval quality and save per-query diagnostics."
    )

    ap.add_argument("eval_set", help="Path to the evaluation JSON file")
    ap.add_argument("--k", type=int, default=20)
    ap.add_argument("--label", default="run")
    ap.add_argument("--out", default=None)

    args = ap.parse_args()

    if args.k < 1:
        ap.error("--k must be at least 1")

    with open(args.eval_set, "r", encoding="utf-8") as f:
        items = json.load(f)

    if not isinstance(items, list) or not items:
        ap.error("Evaluation dataset must be a non-empty JSON list")

    # Warm-up: model loading is excluded from measured query latency.
    _run(items[0], args.k)

    rows = []
    latencies = []
    misses = []
    query_details = []

    for it in items:
        hits, dt = _run(it, args.k)
        latencies.append(dt)

        # Retrieved chunk IDs in their actual ranking order.
        got = [
            h["metadata"]["chunk_index"]
            for h in hits
        ]

        # Expected relevant chunk IDs from the evaluation dataset.
        relevant = set(it["relevant_chunks"])

        # Calculate metrics for this query.
        query_metrics = _score_query(got, relevant, args.k)
        rows.append(query_metrics)

        # Find the rank of each relevant chunk.
        # Rank starts at 1; None means the chunk was not retrieved.
        ranks = {
            chunk_id: got.index(chunk_id) + 1 if chunk_id in got else None
            for chunk_id in sorted(relevant)
        }

        found = relevant.intersection(got)

        # Save per-query diagnostics.
        query_details.append({
            "query": it["query"],
            "relevant_chunks": sorted(relevant),
            "retrieved_chunks": got,
            "relevant_chunk_ranks": ranks,
            "hit_at_k": bool(found),
            "relevant_chunks_found": sorted(found),
            "metrics": query_metrics,
            "latency_ms": round(dt * 1000, 2),
        })

        if not found:
            misses.append(it["query"])

    # Aggregate metrics across all evaluation questions.
    summary = {
        "label": args.label,
        "k": args.k,
        "n_queries": len(items),
    }

    for key in rows[0]:
        summary[key] = round(
            statistics.mean(row[key] for row in rows),
            4,
        )

    sorted_latencies = sorted(latencies)

    summary["latency_ms_mean"] = round(
        1000 * statistics.mean(latencies), 1
    )

    p95_index = int(0.95 * (len(sorted_latencies) - 1))

    summary["latency_ms_p95"] = round(
        1000 * sorted_latencies[p95_index], 1
    )

    # Print aggregate metrics.
    print(json.dumps(summary, indent=2))

    # Print questions with no relevant chunk in the top k.
    print(f"\nQueries with no relevant chunk in top {args.k}: {len(misses)}")

    for query in misses:
        print("  -", ascii(query[:100]))

    # Preserve the original behavior: append one summary per run.
    if args.out:
        with open(args.out, "a", encoding="utf-8") as f:
            f.write(json.dumps(summary) + "\n")

        # Write detailed diagnostics to a separate JSON file.
        if args.out.endswith(".jsonl"):
            details_out = args.out[:-6] + "_details.json"
        else:
            details_out = args.out + "_details.json"

        with open(details_out, "w", encoding="utf-8") as f:
            json.dump(
                query_details,
                f,
                indent=2,
                ensure_ascii=False,
            )

        print(f"\nSummary saved to: {args.out}")
        print(f"Per-query diagnostics saved to: {details_out}")


if __name__ == "__main__":
    main()
