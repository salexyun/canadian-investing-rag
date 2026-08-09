"""Minimal record schema for a fetched page.

Downstream stages (chunking, loading into the knowledge base) read
``data/raw/manifest.jsonl``, which is one JSON object per page shaped
like :class:`FetchedPage`. Keep this schema small and honest — it only
carries what a fetch step can actually know. Chunk-level metadata
(section headers, chunk index, embeddings) belongs to the next stage,
not this one.
"""

from dataclasses import asdict, dataclass
from typing import Optional


@dataclass
class FetchedPage:
    id: str  # slug — matches a Source.id and the raw HTML filename
    url: str
    source_name: str  # e.g. "CRA", "CIRO", "MoneySense"
    tier: str  # "primary" | "secondary" — see data/README.md
    fetch_method: str  # "browser" | "http"
    license: str
    topic: str
    fetched_at: str  # ISO 8601 UTC timestamp of this fetch run
    page_last_updated: Optional[str]  # best-effort, parsed from the page; None if not found
    http_status: Optional[int]
    title: Optional[str]
    raw_html_path: Optional[str]  # POSIX path relative to repo root; None on failure
    content_length: int
    error: Optional[str] = None  # set if the fetch failed; other fields best-effort in that case

    def to_json(self) -> dict:
        return asdict(self)
