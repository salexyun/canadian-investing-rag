"""The retriever the RAG flow actually uses.

Query rewrite -> hybrid (RRF) -> cross-encoder rerank. The empirical
winner from eval/evaluate_retrieval.py's comparison of 6 methods (bm25,
vector, hybrid, vector_rerank, hybrid_rerank, hybrid_rerank_rewrite).
Query rewriting was the single largest jump in the whole investigation —
plain-language hit-rate went 0.571 -> 0.804 — worth the extra LLM call
per query. See TODO.md for the full numbers and the one honest
tradeoff (rewriting is very slightly worse on already-precise jargon
queries; the net gain heavily outweighs it).

This module owns constructing the whole retriever stack (BM25 index +
vector search + Qdrant client + reranker) so callers (the RAG class,
the eval script) don't each wire it up independently.
"""

from __future__ import annotations

from bm25_search import BM25Search
from hybrid_search import HybridSearch
from langfuse.openai import OpenAI  # drop-in wrapper -- traces every .responses.create/.parse call to Langfuse
from query_rewrite import rewrite_query
from reranker import rerank
from vector_search import VectorSearch
from langfuse import observe

CANDIDATE_K = 20  # candidates handed to the cross-encoder before trimming to top_k


class Retriever:
    def __init__(self, hybrid: HybridSearch, llm_client: OpenAI | None = None, candidate_k: int = CANDIDATE_K):
        self.hybrid = hybrid
        self.llm_client = llm_client or OpenAI()
        self.candidate_k = candidate_k

    @classmethod
    def build(cls) -> "Retriever":
        bm25 = BM25Search.build()
        vector = VectorSearch()
        hybrid = HybridSearch(bm25, vector)
        return cls(hybrid)

    @observe(name="retrieve")
    def search(self, query: str, top_k: int = 5) -> list[dict]:
        rewritten = rewrite_query(query, self.llm_client)
        candidates = self.hybrid.search(rewritten, top_k=self.candidate_k)
        return rerank(rewritten, candidates, top_k)
