"""Vector search via Qdrant + the bge-small embedding model.

Extracted from eval/evaluate_retrieval.py rather than reimplemented here
independently — the RAG flow needs to use the literal same retrieval code
that was evaluated, not a second implementation that could silently
drift from what the eval numbers actually measured.
"""

from __future__ import annotations

from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer

EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
COLLECTION_NAME = "canadian_investing_chunks"
QDRANT_URL = "http://localhost:6333"


class VectorSearch:
    def __init__(self, qdrant_url: str = QDRANT_URL):
        self.embedder = SentenceTransformer(EMBEDDING_MODEL)
        self.client = QdrantClient(url=qdrant_url)

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        vec = self.embedder.encode(QUERY_PREFIX + query, normalize_embeddings=True)
        hits = self.client.query_points(collection_name=COLLECTION_NAME, query=vec.tolist(), limit=top_k).points
        return [h.payload for h in hits]
