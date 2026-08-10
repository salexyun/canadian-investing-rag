"""Record schemas for the ingestion pipeline — two layers, deliberately kept separate:

- :class:`FetchedPage` — one per fetched page (``data/raw/manifest.jsonl``).
  Provenance and source-authority context only: what did we fetch, from
  whom, under what jurisdiction, when, and is it still there. Written by
  ``ingestion/fetch.py`` today.

- :class:`Chunk` — one per retrievable unit, several per page
  (``data/processed/chunks.jsonl``, once ``ingestion/pipeline.py``
  exists). Trust/freshness/facet metadata that genuinely varies *within*
  a page — a TFSA page's contribution-limit sentence is a
  ``numeric_fact`` with a real ``effective_date``; the same page's "what
  is a TFSA" paragraph is ``conceptual`` and evergreen. Collapsing these
  onto the page record would lose exactly that distinction, so don't.

A Chunk inherits `source_authority` / `tier` / `jurisdiction` / `url`
from its parent Page rather than re-deriving them — those are page-level
facts, not per-chunk judgment calls. `facets` starts as the page's
`default_facets` and gets refined per chunk once real chunking exists;
this file draws the boundary, not the chunker itself.

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

OGL = "Open Government Licence – Canada"

# One entry per distinct publisher — the single source of truth for
# source_name/tier/license/fetch_method/jurisdiction, all of which are
# fixed properties of *who published this*, not of any individual page
# (verified: every page from a given authority carries the same tier,
# license, fetch method, and — see jurisdiction note below — the same
# default jurisdiction). Registering a source here is deliberate
# friction, not an oversight; sources.make_source() reads from this
# rather than making callers retype these on every page.
#
# jurisdiction here is a *default*, not a fixed fact like the others —
# it means "what this content applies to," not "who wrote it," and a
# publisher's own pages can occasionally need a different jurisdiction
# than their default (make_source() accepts an override for exactly
# that). osc_gsam is the concrete example: OSC is Ontario's regulator,
# but GetSmarterAboutMoney's actual content (investing basics,
# diversification) isn't Ontario-specific — tagging it "on" would risk
# a jurisdiction filter wrongly excluding it for a BC or Quebec user,
# so its default is "none" (applies nationally) rather than "on".
#
# "national" (CIRO) is kept distinct from "federal" (CRA, Bank of
# Canada): CIRO is a self-regulatory body operating under provincial
# securities-commission recognition, not a federal government
# department — conflating the two would misrepresent how Canadian
# securities regulation actually works.
SOURCE_AUTHORITY_INFO: dict[str, dict] = {
    "cra":        {"source_name": "CRA",                       "tier": "primary",   "fetch_method": "browser", "license": OGL,                  "jurisdiction": "federal"},
    # CPP/OAS are administered by Service Canada on behalf of ESDC
    # (Employment and Social Development Canada), not CRA — a
    # different federal department, even though it's the same
    # canada.ca domain. Citing this as "CRA" would misattribute it.
    "esdc":       {"source_name": "Service Canada / ESDC",     "tier": "primary",   "fetch_method": "browser", "license": OGL,                  "jurisdiction": "federal"},
    "ciro":       {"source_name": "CIRO",                      "tier": "primary",   "fetch_method": "browser", "license": "CIRO content",       "jurisdiction": "national"},
    "amf":        {"source_name": "AMF",                       "tier": "primary",   "fetch_method": "browser", "license": "AMF content",        "jurisdiction": "qc"},
    "boc":        {"source_name": "Bank of Canada",            "tier": "primary",   "fetch_method": "http",    "license": "Bank of Canada terms of use", "jurisdiction": "federal"},
    "osc_gsam":   {"source_name": "OSC / GetSmarterAboutMoney", "tier": "primary",  "fetch_method": "http",    "license": "OSC content",        "jurisdiction": "none"},
    "fpcanada":   {"source_name": "FP Canada",                 "tier": "secondary", "fetch_method": "http",    "license": "FP Canada content",  "jurisdiction": "none"},
    "moneysense": {"source_name": "MoneySense",                "tier": "secondary", "fetch_method": "http",    "license": "MoneySense content", "jurisdiction": "none"},
    "rbc":        {"source_name": "RBC",                       "tier": "secondary", "fetch_method": "http",    "license": "RBC content",        "jurisdiction": "none"},
    "td":         {"source_name": "TD",                        "tier": "secondary", "fetch_method": "http",    "license": "TD content",         "jurisdiction": "none"},
    "questrade":  {"source_name": "Questrade",                 "tier": "secondary", "fetch_method": "http",    "license": "Questrade content",  "jurisdiction": "none"},
    # CIPF/CDIC: industry-funded but government-mandated protection
    # schemes (CIPF coverage is a CIRO membership requirement; CDIC is
    # a literal federal Crown corporation) — primary, not secondary,
    # for the same reason CIRO is primary: mandated authority, not a
    # commercial explainer with a product to sell.
    "cipf":       {"source_name": "CIPF",                      "tier": "primary",   "fetch_method": "http",    "license": "CIPF content",       "jurisdiction": "national"},
    "cdic":       {"source_name": "CDIC",                      "tier": "primary",   "fetch_method": "http",    "license": "CDIC content",       "jurisdiction": "federal"},
}

JURISDICTIONS = {"federal", "national", "on", "qc", "bc", "none"}

# Chunk-level only. Drives citation/trust behaviour in the prompt —
# numeric_fact chunks need the tightest primary-source + freshness
# enforcement; conceptual chunks can be more lenient.
CONTENT_TYPES = {"conceptual", "numeric_fact", "procedural", "example"}

# --- Facets -------------------------------------------------------------------
#
# Five dimensions, not one flat tag bag — a chunk about "withdrawing from
# a TFSA" and a chunk about "the dividend tax credit on non-registered
# investments" have nothing in common except both being investing
# content; forcing them into the same tag vocabulary loses the ability
# to filter/facet cleanly (e.g. "show me every numeric_fact chunk about
# RRSP + withdrawing + non_resident"). This also turns "do we have
# coverage?" into a checkable account_type x action matrix instead of an
# eyeballed source list — see data/README.md's coverage-gap findings.
#
# account_type is exhaustive by construction (Canada has exactly these
# registered-account types) and finalized here — it shouldn't need to
# change. The other four are bounded but curated; extend deliberately,
# not by convention drift.

ACCOUNT_TYPES = {
    "tfsa", "rrsp", "rrif", "fhsa", "resp", "rdsp", "lira_lrsp", "prpp",
    "non_registered", "none",
}
# "prpp" (Pooled Registered Pension Plan) added on the breadth-expansion
# pass: found while pulling RRSP subpages, and account_type claims to be
# exhaustive of Canada's registered-account types — leaving out a real
# one because it's niche would break that claim.

TAX_CONCEPTS = {
    "capital_gains", "capital_losses", "superficial_loss", "attribution_rules",
    "contribution_room", "over_contribution_penalty", "withholding_tax",
    "tax_deduction", "tax_credit", "dividend_tax_credit", "oas_clawback",
    "foreign_reporting",  # T1135 / NR4 — a reporting obligation, distinct from withholding_tax (a tax owed)
}

INVESTMENT_VEHICLES = {
    "stocks", "etfs", "mutual_funds", "bonds", "gics", "reits", "options", "crypto",
}

ACTIONS = {
    "contributing", "withdrawing", "transferring", "opening_account",
    "filing_taxes", "calculating_room",
}

# Added on top of the original four facets: this project's whole reason
# for existing is that residency/life-event status changes the answer,
# so that can't be left as just another entry buried in a generic tag
# set — it needs to be filterable on its own.
SPECIAL_SITUATIONS = {"death_and_estates", "divorce_separation", "non_resident"}


@dataclass(frozen=True)
class Facets:
    account_type: str  # required, single-valued — see ACCOUNT_TYPES; "none" for content that isn't about a specific account
    tax_concepts: tuple[str, ...] = ()
    investment_vehicles: tuple[str, ...] = ()
    actions: tuple[str, ...] = ()
    special_situations: tuple[str, ...] = ()

    def to_json(self) -> dict:
        return asdict(self)


def validate_facets(facets: Facets) -> None:
    if facets.account_type not in ACCOUNT_TYPES:
        raise ValueError(f"account_type {facets.account_type!r} not in {sorted(ACCOUNT_TYPES)}")
    _check_subset(facets.tax_concepts, TAX_CONCEPTS, "tax_concepts")
    _check_subset(facets.investment_vehicles, INVESTMENT_VEHICLES, "investment_vehicles")
    _check_subset(facets.actions, ACTIONS, "actions")
    _check_subset(facets.special_situations, SPECIAL_SITUATIONS, "special_situations")


def _check_subset(values: tuple[str, ...], vocab: set[str], field_name: str) -> None:
    unknown = set(values) - vocab
    if unknown:
        raise ValueError(f"{field_name} {sorted(unknown)} not in {sorted(vocab)}")


def validate_source_fields(*, source_authority: str, jurisdiction: str,
                            tier: str, facets: Facets) -> None:
    """Fail loudly on registration mistakes rather than silently ingesting them."""
    if source_authority not in SOURCE_AUTHORITY_INFO:
        raise ValueError(
            f"Unregistered source_authority {source_authority!r} — add it to "
            f"SOURCE_AUTHORITY_INFO in ingestion/schema.py first."
        )
    if jurisdiction not in JURISDICTIONS:
        raise ValueError(f"jurisdiction {jurisdiction!r} not in {sorted(JURISDICTIONS)}")
    if tier not in {"primary", "secondary"}:
        raise ValueError(f"tier must be 'primary' or 'secondary', got {tier!r}")
    validate_facets(facets)


def validate_chunk_fields(*, content_type: str, facets: Facets) -> None:
    if content_type not in CONTENT_TYPES:
        raise ValueError(f"content_type {content_type!r} not in {sorted(CONTENT_TYPES)}")
    validate_facets(facets)


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
    default_facets: Facets  # inherited by this page's chunks unless overridden
    fetched_at: str  # ISO 8601 UTC timestamp of this fetch run
    page_last_updated: Optional[str]  # best-effort last-modified date (dcterms.modified); None if not found
    content_hash: Optional[str]  # sha256 of the raw HTML — lets a re-run detect "this page didn't change"
    http_status: Optional[int]
    title: Optional[str]
    raw_html_path: Optional[str]  # POSIX path relative to repo root; None on failure
    content_length: int
    error: Optional[str] = None  # set if the fetch failed; other fields best-effort in that case

    def to_json(self) -> dict:
        d = asdict(self)
        d["default_facets"] = self.default_facets.to_json()
        return d


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
    facets: Facets  # starts as the page's default_facets, refined per chunk
    text: str
    effective_date: Optional[str] = None  # when this fact became true; None for evergreen/conceptual chunks
    review_date: Optional[str] = None  # when we last confirmed this chunk is still accurate; None until a verification pass runs

    def to_json(self) -> dict:
        d = asdict(self)
        d["facets"] = self.facets.to_json()
        return d
