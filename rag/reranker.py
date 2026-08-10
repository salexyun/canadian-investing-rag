"""Cross-encoder reranking.

A cross-encoder jointly encodes (query, passage) pairs and scores them
directly, rather than comparing separately-computed representations the
way bi-encoder embeddings (vector search) or lexical overlap (BM25) do.
That joint attention is generally much better at nuanced relevance
judgment — which is exactly the gap the retrieval eval found: hybrid's
plain-language MRR (0.362) trails its jargon MRR (0.801) even after
winning overall, and neither BM25's lexical matching nor a fixed
bi-encoder embedding can do much more reasoning about "does this
passage actually answer this paraphrased question" than they already
did at the first stage.

Too slow to run over the full corpus, so it's applied to a first-stage
retrieval's candidate shortlist only, to re-order it.

Model: BAAI/bge-reranker-base — same publisher/family as the bge-small
embedding model already in use; local/free; English-only corpus
doesn't need the heavier multilingual bge-reranker-v2-m3.
"""

from __future__ import annotations

from sentence_transformers import CrossEncoder

MODEL_NAME = "BAAI/bge-reranker-base"

_model: CrossEncoder | None = None


def get_reranker() -> CrossEncoder:
    global _model
    if _model is None:
        _model = CrossEncoder(MODEL_NAME)
    return _model


def rerank(query: str, candidates: list[dict], top_k: int) -> list[dict]:
    if not candidates:
        return []
    model = get_reranker()
    pairs = [(query, c["text"]) for c in candidates]
    scores = model.predict(pairs)
    ranked = sorted(zip(candidates, scores), key=lambda x: x[1], reverse=True)
    return [c for c, _ in ranked[:top_k]]
