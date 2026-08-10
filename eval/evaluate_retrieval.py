"""Evaluate retrieval approaches: BM25 vs vector vs hybrid (RRF) vs reranked variants.

Runs the 112-question ground-truth set (eval/retrieval_ground_truth.jsonl)
against all five methods and reports hit-rate/MRR — the exact metrics
and formulas the coursework's Module 4 uses — both overall and split by
`phrasing_style` (jargon vs plain_language), since the whole reason for
building multiple methods instead of just picking one was the hypothesis
that BM25 and vector search fail on different query styles. An aggregate
score would hide exactly the effect this is supposed to measure.

Uses the same rag/ retrieval modules the production RAG flow uses
(bm25_search, vector_search, hybrid_search, reranker) rather than a
second implementation — the eval numbers need to describe the code
that's actually deployed, not a reimplementation that could drift.

Usage:
    python eval/evaluate_retrieval.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT.parent / "rag"))

from bm25_search import BM25Search  # noqa: E402
from hybrid_search import HybridSearch  # noqa: E402
from query_rewrite import rewrite_query  # noqa: E402
from reranker import rerank  # noqa: E402
from vector_search import VectorSearch  # noqa: E402
from dotenv import load_dotenv  # noqa: E402
from openai import OpenAI  # noqa: E402

load_dotenv()

GROUND_TRUTH_PATH = Path(__file__).resolve().parent / "retrieval_ground_truth.jsonl"
RESULTS_PATH = Path(__file__).resolve().parent / "retrieval_eval_results.json"

TOP_K_FINAL = 5  # results actually evaluated for hit-rate/MRR
TOP_K_RERANK_CANDIDATES = 20  # candidates handed to the cross-encoder before trimming to TOP_K_FINAL


def load_ground_truth() -> list[dict]:
    return [json.loads(line) for line in GROUND_TRUTH_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]


def build_rewrite_cache(questions: list[dict]) -> dict[str, str]:
    """Precompute rewrites once per unique question, not once per slice
    evaluation — the same 112 questions get evaluated across overlapping
    subsets (overall, jargon, plain_language, numeric_fact), and each is
    an LLM call; caching keeps this to exactly 112 calls, not 4x that."""
    from concurrent.futures import ThreadPoolExecutor

    client = OpenAI()
    unique_questions = list({q["question"] for q in questions})
    cache: dict[str, str] = {}
    print(f"Pre-computing {len(unique_questions)} query rewrites...")
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = pool.map(lambda q: (q, rewrite_query(q, client)), unique_questions)
        for original, rewritten in results:
            cache[original] = rewritten
    return cache


def build_methods(questions: list[dict]) -> dict:
    print("Building BM25 index...")
    bm25 = BM25Search.build()
    print("Loading embedding model...")
    vector = VectorSearch()
    hybrid = HybridSearch(bm25, vector)
    rewrite_cache = build_rewrite_cache(questions)

    def bm25_search(query: str, top_k: int) -> list[dict]:
        return [r.chunk for r in bm25.search(query, top_k=top_k)]

    def vector_search(query: str, top_k: int) -> list[dict]:
        return vector.search(query, top_k=top_k)

    def hybrid_search(query: str, top_k: int) -> list[dict]:
        return hybrid.search(query, top_k=top_k)

    def vector_rerank_search(query: str, top_k: int) -> list[dict]:
        candidates = vector.search(query, top_k=TOP_K_RERANK_CANDIDATES)
        return rerank(query, candidates, top_k)

    def hybrid_rerank_search(query: str, top_k: int) -> list[dict]:
        candidates = hybrid.search(query, top_k=TOP_K_RERANK_CANDIDATES)
        return rerank(query, candidates, top_k)

    def hybrid_rerank_rewrite_search(query: str, top_k: int) -> list[dict]:
        rewritten = rewrite_cache.get(query, query)
        candidates = hybrid.search(rewritten, top_k=TOP_K_RERANK_CANDIDATES)
        return rerank(rewritten, candidates, top_k)

    return {
        "bm25": bm25_search,
        "vector": vector_search,
        "hybrid": hybrid_search,
        "vector_rerank": vector_rerank_search,
        "hybrid_rerank": hybrid_rerank_search,
        "hybrid_rerank_rewrite": hybrid_rerank_rewrite_search,
    }


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

    methods = build_methods(questions)
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
