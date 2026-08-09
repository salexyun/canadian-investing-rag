"""Record schemas for the ingestion pipeline — two layers, deliberately kept separate:

- :class:`FetchedPage` — one per fetched page (``data/raw/manifest.jsonl``).
  Provenance and source-authority context only: what did we fetch, from
  whom, under what jurisdiction, when, and is it still there. Written by
  ``ingestion/fetch.py`` today.

- :class:`Chunk` — one per retrievable unit, several per page
  (``data/processed/chunks.jsonl``, once ``ingestion/pipeline.py``
  exists). Trust/freshness/topic metadata that genuinely varies *within*
  a page — a TFSA page's contribution-limit sentence is a
  ``numeric_fact`` with a real ``effective_date``; the same page's "what
  is a TFSA" paragraph is ``conceptual`` and evergreen. Collapsing these
  onto the page record would lose exactly that distinction, so don't.

A Chunk inherits `source_authority` / `tier` / `jurisdiction` / `url`
from its parent Page rather than re-deriving them — those are page-level
facts, not per-chunk judgment calls. `topic_tags` starts as the page's
`default_topic_tags` and gets refined per chunk once real chunking
exists; this file draws the boundary, not the chunker itself.

Controlled vocabularies live here too, and are meant to be enforced
(via ``validate_*``) rather than just documented in a comment — the
whole point of this schema is that a typo'd jurisdiction or an
unregistered source authority fails loudly instead of silently
corrupting trust-tiering downstream.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional

# --- Controlled vocabularies -------------------------------------------------

# One slug per distinct publisher. Adding a new source means registering
# it here on purpose — that friction is intentional, not an oversight.
SOURCE_AUTHORITIES = {
    "cra", "ciro", "amf", "boc", "osc_gsam",           # primary
    "fpcanada", "moneysense", "rbc", "td", "questrade",  # secondary
}

# Whose legal/regulatory authority this content speaks under — distinct
# from *tier*, which is about how authoritative we treat it, not who
# issued it. "national" (CIRO) is kept separate from "federal" (CRA,
# Bank of Canada) on purpose: CIRO is a self-regulatory body operating
# under provincial securities-commission recognition, not a federal
# government department — conflating the two would misrepresent how
# Canadian securities regulation actually works, which is precisely the
# kind of inaccuracy this schema exists to prevent.
JURISDICTIONS = {"federal", "national", "on", "qc", "bc", "none"}

# Chunk-level only. Drives citation/trust behaviour in the prompt —
# numeric_fact chunks need the tightest primary-source + freshness
# enforcement; conceptual chunks can be more lenient.
CONTENT_TYPES = {"conceptual", "numeric_fact", "procedural", "example"}

# Every source/chunk must carry >=1 account-type tag (enables a
# programmatic account_type x subtopic coverage matrix instead of
# eyeballing sources.py) plus any number of subtopic tags.
ACCOUNT_TYPE_TAGS = {"tfsa", "rrsp", "fhsa", "resp", "general_investing", "regulatory"}
SUBTOPIC_TAGS = {
    "eligibility", "contribution_room", "over_contribution_penalty",
    "withdrawals", "transfers", "taxation", "death_and_estates",
    "divorce_separation", "non_resident", "fraud_protection",
    "dealer_regulation", "complaints", "diversification",
    "macro_context", "practical_howto",
}
TOPIC_TAGS_VOCAB = ACCOUNT_TYPE_TAGS | SUBTOPIC_TAGS


def validate_source_fields(*, source_authority: str, jurisdiction: str,
                            tier: str, topic_tags: list[str]) -> None:
    """Fail loudly on registration mistakes rather than silently ingesting them."""
    if source_authority not in SOURCE_AUTHORITIES:
        raise ValueError(
            f"Unregistered source_authority {source_authority!r} — add it to "
            f"SOURCE_AUTHORITIES in ingestion/schema.py first."
        )
    if jurisdiction not in JURISDICTIONS:
        raise ValueError(f"jurisdiction {jurisdiction!r} not in {sorted(JURISDICTIONS)}")
    if tier not in {"primary", "secondary"}:
        raise ValueError(f"tier must be 'primary' or 'secondary', got {tier!r}")
    unknown = set(topic_tags) - TOPIC_TAGS_VOCAB
    if unknown:
        raise ValueError(f"topic_tags {sorted(unknown)} not in TOPIC_TAGS_VOCAB")
    if not (set(topic_tags) & ACCOUNT_TYPE_TAGS):
        raise ValueError(f"topic_tags {topic_tags} must include >=1 of {sorted(ACCOUNT_TYPE_TAGS)}")


def validate_chunk_fields(*, content_type: str, topic_tags: list[str]) -> None:
    if content_type not in CONTENT_TYPES:
        raise ValueError(f"content_type {content_type!r} not in {sorted(CONTENT_TYPES)}")
    unknown = set(topic_tags) - TOPIC_TAGS_VOCAB
    if unknown:
        raise ValueError(f"topic_tags {sorted(unknown)} not in TOPIC_TAGS_VOCAB")
    if not (set(topic_tags) & ACCOUNT_TYPE_TAGS):
        raise ValueError(f"topic_tags {topic_tags} must include >=1 of {sorted(ACCOUNT_TYPE_TAGS)}")


# --- Page layer ---------------------------------------------------------------


@dataclass
class FetchedPage:
    id: str  # slug — matches a Source.id and the raw HTML filename
    url: str
    source_name: str  # human-readable, e.g. "CRA" — for display
    source_authority: str  # normalized slug, e.g. "cra" — for filtering/joins; see SOURCE_AUTHORITIES
    jurisdiction: str  # see JURISDICTIONS
    tier: str  # "primary" | "secondary" — see data/README.md
    fetch_method: str  # "browser" | "http"
    license: str
    topic: str  # human-readable description, for reading sources.py
    default_topic_tags: list[str]  # inherited by this page's chunks unless overridden; see TOPIC_TAGS_VOCAB
    fetched_at: str  # ISO 8601 UTC timestamp of this fetch run
    page_issued: Optional[str]  # best-effort original-publish date (dcterms.issued); None if not found
    page_last_updated: Optional[str]  # best-effort last-modified date (dcterms.modified); None if not found
    content_hash: Optional[str]  # sha256 of the raw HTML — lets a re-run detect "this page didn't change"
    http_status: Optional[int]
    title: Optional[str]
    raw_html_path: Optional[str]  # POSIX path relative to repo root; None on failure
    content_length: int
    error: Optional[str] = None  # set if the fetch failed; other fields best-effort in that case

    def to_json(self) -> dict:
        return asdict(self)


# --- Chunk layer (draft — ingestion/pipeline.py doesn't exist yet) ------------


@dataclass
class Chunk:
    chunk_id: str  # f"{page_id}::{chunk_index}"
    page_id: str  # FK to FetchedPage.id
    chunk_index: int
    url: str  # carried down from the page, for direct citation
    source_authority: str  # carried down from the page — never overridden per-chunk
    tier: str  # carried down from the page
    jurisdiction: str  # carried down from the page; override only if a chunk genuinely covers a different jurisdiction than its page's default
    content_type: str  # "conceptual" | "numeric_fact" | "procedural" | "example"
    topic_tags: list[str]  # starts as the page's default_topic_tags, refined per chunk
    text: str
    effective_date: Optional[str] = None  # when this fact became true; None for evergreen/conceptual chunks
    review_date: Optional[str] = None  # when we last confirmed this chunk is still accurate; None until a verification pass runs

    def to_json(self) -> dict:
        return asdict(self)
