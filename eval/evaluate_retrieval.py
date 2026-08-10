"""Evaluate retrieval approaches: BM25 vs vector vs hybrid (RRF).

Runs the 112-question ground-truth set (eval/retrieval_ground_truth.jsonl)
against all three methods and reports hit-rate/MRR — the exact metrics
and formulas the coursework's Module 4 uses — both overall and split by
`phrasing_style` (jargon vs plain_language), since the whole reason for
building three separate methods instead of just picking one was the
hypothesis that BM25 and vector search fail on different query styles.
An aggregate score would hide exactly the effect this is supposed to
measure.

Hybrid uses Reciprocal Rank Fusion, same technique and formula as the
coursework's Module 2 homework (Q6):
    score[doc] += 1 / (k + rank)   for each result list the doc appears in

Usage:
    python eval/evaluate_retrieval.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT.parent / "rag"))

from bm25_search import BM25Search  # noqa: E402

GROUND_TRUTH_PATH = Path(__file__).resolve().parent / "retrieval_ground_truth.jsonl"
RESULTS_PATH = Path(__file__).resolve().parent / "retrieval_eval_results.json"

EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
COLLECTION_NAME = "canadian_investing_chunks"
QDRANT_URL = "http://localhost:6333"

TOP_K_FINAL = 5  # results actually evaluated for hit-rate/MRR
TOP_K_CANDIDATES = 10  # candidates each method contributes to RRF fusion
RRF_K = 60  # same constant the coursework used


def load_ground_truth() -> list[dict]:
    return [json.loads(line) for line in GROUND_TRUTH_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]


class Retrievers:
    def __init__(self):
        print("Building BM25 index...")
        self.bm25 = BM25Search.build()
        print(f"Loading embedding model {EMBEDDING_MODEL}...")
        self.embedder = SentenceTransformer(EMBEDDING_MODEL)
        self.qdrant = QdrantClient(url=QDRANT_URL)

    def bm25_search(self, query: str, top_k: int) -> list[dict]:
        return [r.chunk for r in self.bm25.search(query, top_k=top_k)]

    def vector_search(self, query: str, top_k: int) -> list[dict]:
        vec = self.embedder.encode(QUERY_PREFIX + query, normalize_embeddings=True)
        hits = self.qdrant.query_points(collection_name=COLLECTION_NAME, query=vec.tolist(), limit=top_k).points
        return [h.payload for h in hits]

    def hybrid_search(self, query: str, top_k: int) -> list[dict]:
        result_lists = [
            self.bm25_search(query, TOP_K_CANDIDATES),
            self.vector_search(query, TOP_K_CANDIDATES),
        ]
        scores: dict[str, float] = {}
        docs: dict[str, dict] = {}
        for results in result_lists:
            for rank, doc in enumerate(results):
                key = doc["chunk_id"]
                scores[key] = scores.get(key, 0) + 1 / (RRF_K + rank)
                docs[key] = doc
        ranked = sorted(scores, key=scores.get, reverse=True)
        return [docs[key] for key in ranked[:top_k]]


def compute_relevance(question: dict, search_fn) -> list[int]:
    results = search_fn(question["question"], TOP_K_FINAL)
    return [int(r["chunk_id"] == question["chunk_id"]) for r in results]


def hit_rate(relevance: list[list[int]]) -> float:
    return sum(1 for line in relevance if 1 in line) / len(relevance)


def mrr(relevance: list[list[int]]) -> float:
    total = 0.0
    for line in relevance:
        for rank, val in enumerate(line):
            if val == 1:
                total += 1 / (rank + 1)
                break
    return total / len(relevance)


def evaluate(questions: list[dict], search_fn) -> dict:
    relevance = [compute_relevance(q, search_fn) for q in questions]
    return {"hit_rate": hit_rate(relevance), "mrr": mrr(relevance), "n": len(questions)}


def main() -> int:
    questions = load_ground_truth()
    print(f"Loaded {len(questions)} ground-truth questions\n")

    retrievers = Retrievers()
    methods = {
        "bm25": retrievers.bm25_search,
        "vector": retrievers.vector_search,
        "hybrid": retrievers.hybrid_search,
    }

    results: dict[str, dict] = {}

    print("\n=== Overall ===")
    for name, fn in methods.items():
        r = evaluate(questions, fn)
        results[name] = {"overall": r}
        print(f"  {name:8} hit_rate={r['hit_rate']:.3f}  mrr={r['mrr']:.3f}  (n={r['n']})")

    for style in ["jargon", "plain_language"]:
        subset = [q for q in questions if q["phrasing_style"] == style]
        print(f"\n=== phrasing_style = {style} (n={len(subset)}) ===")
        for name, fn in methods.items():
            r = evaluate(subset, fn)
            results[name][style] = r
            print(f"  {name:8} hit_rate={r['hit_rate']:.3f}  mrr={r['mrr']:.3f}")

    numeric_fact = [q for q in questions if q["content_type"] == "numeric_fact"]
    print(f"\n=== content_type = numeric_fact (n={len(numeric_fact)}) ===")
    for name, fn in methods.items():
        r = evaluate(numeric_fact, fn)
        results[name]["numeric_fact"] = r
        print(f"  {name:8} hit_rate={r['hit_rate']:.3f}  mrr={r['mrr']:.3f}")

    winner = max(results, key=lambda m: results[m]["overall"]["mrr"])
    print(f"\nBest overall (by MRR): {winner}")

    RESULTS_PATH.write_text(json.dumps({"results": results, "winner": winner}, indent=2), encoding="utf-8")
    print(f"Results written to {RESULTS_PATH.relative_to(REPO_ROOT.parent)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
