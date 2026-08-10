"""The retriever the RAG flow actually uses.

Hybrid (RRF) + cross-encoder reranking — the empirical winner from
eval/evaluate_retrieval.py's comparison of 5 methods (bm25, vector,
hybrid, vector_rerank, hybrid_rerank). Not just best on average: it won
on every slice tested (overall, jargon-exact, plain-language, and
numeric_fact), after reranking specifically closed a gap plain hybrid
had on the plain-language slice. See TODO.md for the full numbers.

This module owns constructing the whole retriever stack (BM25 index +
vector search + Qdrant client + reranker) so callers (the RAG class,
the eval script) don't each wire it up independently.
"""

from __future__ import annotations

from bm25_search import BM25Search
from hybrid_search import HybridSearch
from reranker import rerank
from vector_search import VectorSearch

CANDIDATE_K = 20  # candidates handed to the cross-encoder before trimming to top_k


class Retriever:
    def __init__(self, hybrid: HybridSearch, candidate_k: int = CANDIDATE_K):
        self.hybrid = hybrid
        self.candidate_k = candidate_k

    @classmethod
    def build(cls) -> "Retriever":
        bm25 = BM25Search.build()
        vector = VectorSearch()
        hybrid = HybridSearch(bm25, vector)
        return cls(hybrid)

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        candidates = self.hybrid.search(query, top_k=self.candidate_k)
        return rerank(query, candidates, top_k)
