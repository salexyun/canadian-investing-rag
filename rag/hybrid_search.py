"""Hybrid search — Reciprocal Rank Fusion of BM25 + vector search.

Same technique and formula as the coursework's Module 2 homework (Q6):
    score[doc] += 1 / (k + rank)   for each result list the doc appears in
"""

from __future__ import annotations

from bm25_search import BM25Search
from vector_search import VectorSearch

RRF_K = 60  # same constant the coursework used
DEFAULT_CANDIDATE_K = 10  # candidates each underlying method contributes before fusion


class HybridSearch:
    def __init__(self, bm25: BM25Search, vector: VectorSearch):
        self.bm25 = bm25
        self.vector = vector

    def search(self, query: str, top_k: int = 5, candidate_k: int = DEFAULT_CANDIDATE_K) -> list[dict]:
        result_lists = [
            [r.chunk for r in self.bm25.search(query, top_k=candidate_k)],
            self.vector.search(query, top_k=candidate_k),
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
