"""Embed step of the ingestion pipeline.

Reads ``data/processed/chunks.jsonl`` (written by ``chunk.py``), embeds
each chunk's text, and upserts into Qdrant with the full chunk record as
payload — so a search result is self-contained (citation, tier, facets,
content_type) without a second lookup.

Model: BAAI/bge-small-en-v1.5 (384-dim), chosen over the more commonly
used all-MiniLM-L6-v2 for stronger retrieval-benchmark performance at a
comparable size. Local/free — no per-embedding API cost, which matters
here since retrieval eval means re-embedding queries repeatedly while
tuning.

BGE models are trained with an asymmetric convention: passages are
embedded as-is, but queries need an instruction prefix
("Represent this sentence for searching relevant passages: ") for the
embedding space to align correctly. This script embeds passages (no
prefix) — retrieval code must apply the prefix to queries, not here.

Known limitation, not silently ignored: 13/1052 chunks (1.2%) exceed the
model's 512-token max_seq_length (our chunker targets ~1200 chars/section,
which is usually well under 512 tokens for English prose, but a few
number-dense financial/legal chunks push over). sentence-transformers
truncates automatically rather than erroring — the tail of those 13
chunks won't influence their embedding, though the full text is still
stored and returned. Small and bounded; not worth re-tuning the chunker
for a 1.2% tail.

Usage:
    python ingestion/load_vector_store.py
    python ingestion/load_vector_store.py --recreate   # drop and rebuild the collection
"""

from __future__ import annotations

import argparse
import json
import os
import uuid
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from sentence_transformers import SentenceTransformer

REPO_ROOT = Path(__file__).resolve().parent.parent
CHUNKS_PATH = REPO_ROOT / "data" / "processed" / "chunks.jsonl"

MODEL_NAME = "BAAI/bge-small-en-v1.5"
EMBEDDING_DIM = 384
COLLECTION_NAME = "canadian_investing_chunks"
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
BATCH_SIZE = 64


def chunk_point_id(chunk_id: str) -> str:
    """Deterministic UUID from chunk_id — re-running the loader upserts
    (updates) the same points rather than creating duplicates."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))


def load_chunks() -> list[dict]:
    if not CHUNKS_PATH.exists():
        raise SystemExit(f"No chunks at {CHUNKS_PATH} — run chunk.py first.")
    return [json.loads(line) for line in CHUNKS_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]


def ensure_collection(client: QdrantClient, recreate: bool) -> None:
    exists = client.collection_exists(COLLECTION_NAME)
    if exists and recreate:
        client.delete_collection(COLLECTION_NAME)
        exists = False
    if not exists:
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recreate", action="store_true", help="Drop and rebuild the collection")
    args = parser.parse_args()

    chunks = load_chunks()
    print(f"Loaded {len(chunks)} chunks from {CHUNKS_PATH.relative_to(REPO_ROOT)}")

    print(f"Loading embedding model {MODEL_NAME}...")
    model = SentenceTransformer(MODEL_NAME)

    client = QdrantClient(url=QDRANT_URL)
    ensure_collection(client, recreate=args.recreate)

    n_uploaded = 0
    for i in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[i : i + BATCH_SIZE]
        texts = [c["text"] for c in batch]
        vectors = model.encode(texts, show_progress_bar=False, normalize_embeddings=True)

        points = [
            PointStruct(
                id=chunk_point_id(c["chunk_id"]),
                vector=vector.tolist(),
                payload=c,
            )
            for c, vector in zip(batch, vectors)
        ]
        client.upsert(collection_name=COLLECTION_NAME, points=points)
        n_uploaded += len(points)
        print(f"  upserted {n_uploaded}/{len(chunks)}", end="\r")

    print()
    info = client.get_collection(COLLECTION_NAME)
    print(f"Collection '{COLLECTION_NAME}': {info.points_count} points, vector size {EMBEDDING_DIM}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
