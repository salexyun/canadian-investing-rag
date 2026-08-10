"""Keyword/BM25 retrieval — a genuinely separate, independently-scored
method from the vector search in ingestion/load_vector_store.py, not a
variant of it, so the two can be fairly compared (and later fused via RRF)
in the retrieval evaluation.

No embeddings involved: BM25 is pure lexical term matching (tokenize,
score by term frequency weighted by inverse document frequency, normalized
for document length). This is exactly why it's worth having alongside
vector search for this corpus — it nails jargon-exact queries ("TFSA
contribution room 2026") via exact token overlap, and doesn't blur
near-identical templated sentences across account types the way the
vector search's embeddings risk doing (see data/README.md's numeric_fact
collision-risk finding). It will conversely miss paraphrased queries with
no shared vocabulary ("tax-free account for newcomers") — that gap is
what vector search and hybrid exist to cover.

In-memory, rebuilt on load rather than persisted: rank-bm25 builds a
1,052-document BM25Okapi index in well under a second, so there's no
reason to add index-persistence complexity for this corpus size.

Usage:
    from bm25_search import BM25Search
    index = BM25Search.build()
    index.search("TFSA contribution limit 2026", top_k=5)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from rank_bm25 import BM25Okapi

REPO_ROOT = Path(__file__).resolve().parent.parent
CHUNKS_PATH = REPO_ROOT / "data" / "processed" / "chunks.jsonl"

_TOKEN_RE = re.compile(r"[a-z0-9]+(?:[.,]\d+)?")


def tokenize(text: str) -> list[str]:
    """Lowercase word/number tokenizer. Keeps decimal/comma-grouped
    numbers as single tokens (e.g. "7,000" doesn't split into "7" and
    "000") since dollar amounts are exactly the kind of exact-match
    token this corpus needs BM25 to get right."""
    return _TOKEN_RE.findall(text.lower())


@dataclass
class ScoredChunk:
    chunk: dict
    score: float


class BM25Search:
    def __init__(self, chunks: list[dict], bm25: BM25Okapi):
        self.chunks = chunks
        self.bm25 = bm25

    @classmethod
    def build(cls, chunks_path: Path = CHUNKS_PATH) -> "BM25Search":
        if not chunks_path.exists():
            raise SystemExit(f"No chunks at {chunks_path} — run ingestion/pipeline.py first.")
        chunks = [json.loads(line) for line in chunks_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        tokenized = [tokenize(c["text"]) for c in chunks]
        bm25 = BM25Okapi(tokenized)
        return cls(chunks, bm25)

    def search(self, query: str, top_k: int = 5) -> list[ScoredChunk]:
        scores = self.bm25.get_scores(tokenize(query))
        ranked_idx = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
        return [ScoredChunk(chunk=self.chunks[i], score=float(scores[i])) for i in ranked_idx]


if __name__ == "__main__":
    index = BM25Search.build()
    print(f"Built BM25 index over {len(index.chunks)} chunks")

    for q in [
        "What is the TFSA contribution limit for 2026?",
        "I just moved to Canada, can I put money in a tax-free account?",
        "what happens to my investments if I leave Canada",
    ]:
        print(f"\n=== {q!r} ===")
        for r in index.search(q, top_k=3):
            at = r.chunk["facets"]["account_type"]
            print(f"  score={r.score:.2f} [{at}] {r.chunk['text'][:100]!r}")
