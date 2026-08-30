"""Chunk step of the ingestion pipeline.

Reads ``data/raw/manifest.jsonl`` (written by ``fetch.py``), chunks each
successfully-fetched page's raw HTML, and writes ``data/processed/chunks.jsonl``
— one :class:`schema.Chunk` JSON record per line.

Strategy (see data/README.md for the reasoning):

- Extract ``<main>``, strip known boilerplate (script/style/nav, the
  WET-BOEW "Most requested"/"Services and information"/page-details/
  alert-banner blocks CRA and ESDC pages share, plus a generic
  link-density heuristic that catches similar nav-list blocks on
  non-government pages).
- Split primarily at H2 boundaries (H3 nested inside long H2 sections)
  — real document structure, not a fixed-size window that could cut a
  number and its effective date in half.
- No artificial minimum chunk size: a genuine one-sentence answer is a
  good chunk. Long sections do get sub-split (~1200 char target,
  small overlap), preferring the document's own numbered
  subsections (folios) over an arbitrary cut.
- ``content_type`` via rule-based heuristics (dollar/percent/limit
  language -> numeric_fact; imperative "how to" -> procedural;
  "for example" -> example; else conceptual) — cheap and debuggable,
  not an LLM call per chunk.
- ``effective_date`` extraction (regex for a date near a dollar
  amount) only runs on chunks already classified numeric_fact, to
  keep false positives down.
- ``facets`` inherit from the page's ``default_facets`` unmodified —
  safe here specifically because the corpus is already mostly narrow,
  single-topic leaf pages (that was the point of the content-quality
  audit pass).

Usage:
    python ingestion/chunk.py
    python ingestion/chunk.py --only cra_tfsa_what cra_tfsa_calculate_room
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup
from bs4.element import Tag

from schema import Chunk, Facets, validate_chunk_fields

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_RAW = REPO_ROOT / "data" / "raw"
DATA_PROCESSED = REPO_ROOT / "data" / "processed"
MANIFEST_PATH = DATA_RAW / "manifest.jsonl"
CHUNKS_PATH = DATA_PROCESSED / "chunks.jsonl"

# WET-BOEW (Government of Canada template) boilerplate blocks — shared by
# CRA and ESDC pages. Harmless no-ops on non-government pages (nothing to
# match), so this list doesn't need a per-source-authority branch.
BOILERPLATE_CLASSES = ["gc-most-requested", "gc-srvinfo", "pagedetails", "alert"]

MAX_SECTION_CHARS = 1200
OVERLAP_CHARS = 150
LINK_DENSITY_THRESHOLD = 0.6  # a block is treated as pure navigation above this
# Below this, a "section" is boilerplate noise that slipped through stripping
# (breadcrumbs like "Home / Stocks", attribution lines like "From: Canada
# Revenue Agency", stray TOC fragments) rather than a real short answer — every
# genuine short-but-complete chunk found during review was 138+ chars.
MIN_CHUNK_CHARS = 40


def load_main(html: str) -> Tag | None:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup.find_all(["script", "style", "nav"]):
        tag.decompose()
    for cls in BOILERPLATE_CLASSES:
        for el in soup.find_all(class_=cls):
            el.decompose()
    return soup.find("main") or soup.find("article") or soup.body


def _link_density(el: Tag) -> float:
    total = len(el.get_text(strip=True))
    if total == 0:
        return 0.0
    link_text = sum(len(a.get_text(strip=True)) for a in el.find_all("a"))
    return link_text / total


_COOKIE_CONSENT_RE = re.compile(
    r"\bcookies\b.{0,80}\b(privacy policy|continue|consent)\b|"
    r"select your language|veuillez s[ée]lectionner votre langue",
    re.I,
)


def _is_nav_block(el: Tag) -> bool:
    """A block is navigation/chrome, not content: mostly link text with
    more than one link (a single inline link inside a real sentence, e.g.
    "...registered retirement savings plan (RRSP)...", must not trigger
    this), or a cookie-consent / language-selector banner — found on CIPF,
    whose template differs from the government WET-BOEW pages the other
    boilerplate stripping targets, and likely to recur on other secondary
    sources with their own templates."""
    text = el.get_text(" ", strip=True)
    if _COOKIE_CONSENT_RE.search(text):
        return True
    if len(el.find_all("a")) < 2:
        return False
    return _link_density(el) > LINK_DENSITY_THRESHOLD


def _block_text(el: Tag) -> str:
    """Text of a block, with nested nav-list sub-blocks excluded."""
    if _is_nav_block(el):
        return ""
    parts = []
    for child in el.find_all(["p", "li", "dt", "dd"], recursive=False) or [el]:
        if isinstance(child, Tag) and _is_nav_block(child):
            continue
        parts.append(child.get_text(" ", strip=True))
    text = " ".join(p for p in parts if p)
    return text if text else (el.get_text(" ", strip=True) if not _is_nav_block(el) else "")


def split_into_sections(main: Tag) -> list[tuple[str, str]]:
    """Returns [(heading, section_text), ...], splitting at h1/h2.

    Walks the document in flattened order rather than via sibling
    traversal from each heading — CRA pages wrap each heading in its
    own single-child container div (no siblings of its own), with
    the real content living in sibling containers one level up, at an
    inconsistent nesting depth from page to page. Sibling-walking from
    the heading missed real content entirely on pages shaped that way
    (confirmed: several pages known to have real prose produced zero
    sections before this fix). Document order is robust to nesting
    depth; sibling relationships aren't.
    """
    elements = main.find_all(["h1", "h2", "p", "ul", "ol", "dl"])

    sections: list[tuple[str, str]] = []
    current_heading = ""
    current_parts: list[str] = []

    def flush() -> None:
        text = " ".join(p for p in current_parts if p).strip()
        if text:
            sections.append((current_heading, text))

    for el in elements:
        if el.name in ("h1", "h2"):
            flush()
            current_heading = el.get_text(" ", strip=True)
            current_parts = []
        elif el.name in ("ul", "ol", "dl"):
            if _is_nav_block(el):
                continue
            t = _block_text(el)
            if t:
                current_parts.append(t)
        elif el.name == "p":
            # skip <p> tags that are just wrappers around a <ul>/<ol> we
            # already handled, or that sit inside one (avoid double-counting)
            if el.find_parent(["ul", "ol", "dl"]) is not None:
                continue
            if _is_nav_block(el):
                continue
            t = el.get_text(" ", strip=True)
            if t:
                current_parts.append(t)
    flush()

    return sections


def sub_split(text: str, max_chars: int = MAX_SECTION_CHARS, overlap: int = OVERLAP_CHARS) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    # Split on sentence boundaries so we don't cut mid-sentence, and overlap
    # by whole trailing sentences (not a raw character tail-slice, which
    # produced garbled mid-word/mid-sentence starts like "in your CRA
    # account. The TFSA information...").
    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for sent in sentences:
        if current and current_len + len(sent) + 1 > max_chars:
            chunks.append(" ".join(current).strip())
            # carry forward whole trailing sentences totalling ~`overlap` chars
            carry: list[str] = []
            carry_len = 0
            for s in reversed(current):
                if carry_len + len(s) > overlap:
                    break
                carry.insert(0, s)
                carry_len += len(s) + 1
            current = carry + [sent]
            current_len = sum(len(s) + 1 for s in current)
        else:
            current.append(sent)
            current_len += len(sent) + 1
    if current:
        chunks.append(" ".join(current).strip())
    return chunks


_MONEY_RE = re.compile(r"\$[\d,]+(?:\.\d+)?|\b\d{1,3}%\b")
_LIMIT_WORDS_RE = re.compile(r"\b(limit|maximum|minimum|deduction limit|dollar limit|contribution room)\b", re.I)
_HOWTO_RE = re.compile(r"^(how to|to (contribute|withdraw|open|transfer|set up|claim))\b", re.I)
# CRA's actual worked-example marker is "Example:" (a standalone heading-style
# label, capital E + colon), not prose "for example" — found by inspecting real
# chunk output: naive numeric_fact detection was misclassifying these (a
# narrated scenario with a named person and several dollar amounts) as
# numeric_fact, and then extracting the *example's* years as if they were the
# real effective_date of a current rule. Checked first, highest priority.
_EXAMPLE_RE = re.compile(r"\bExample:|for example\b|for instance\b")
_DATE_NEAR_MONEY_RE = re.compile(
    r"(?:on |effective |as of )?(January|February|March|April|May|June|July|August|"
    r"September|October|November|December)\s+\d{1,2},?\s+(\d{4})",
    re.I,
)
_YEAR_RE = re.compile(r"\b(20\d{2})\b")


def classify_content_type(heading: str, text: str) -> str:
    if _EXAMPLE_RE.search(text):
        return "example"
    # Numeric facts are checked against the *lead* text only (heading + first
    # ~200 chars) — the actual figure is CRA's house style to state upfront
    # ("The TFSA dollar limit for 2026 is $7,000..."). Checking the whole
    # chunk let an incidental number three sentences into a conceptual
    # explainer misclassify the whole thing.
    lead = heading + " " + text[:200]
    if _MONEY_RE.search(lead) or _LIMIT_WORDS_RE.search(lead):
        return "numeric_fact"
    if _HOWTO_RE.search(heading) or _HOWTO_RE.search(text[:60]):
        return "procedural"
    return "conceptual"


def extract_effective_date(text: str) -> str | None:
    # Scoped to a date/year found near one of the LIMIT_WORDS, not anywhere a
    # dollar amount happens to appear — a numeric_fact chunk can still contain
    # an unrelated year (e.g. a cross-reference), and this must not pick that
    # up as if it were this fact's effective date.
    for m in re.finditer(r"\b(limit|deduction limit|dollar limit|contribution room)\b", text, re.I):
        window = text[max(0, m.start() - 120): m.end() + 120]
        dm = _DATE_NEAR_MONEY_RE.search(window)
        if dm:
            month, year = dm.group(1), dm.group(2)
            try:
                from datetime import datetime
                dt = datetime.strptime(f"{month} {year}", "%B %Y")
                full = re.search(rf"{month}\s+(\d{{1,2}}),?\s+{year}", window, re.I)
                day = full.group(1) if full else "1"
                return f"{year}-{dt.month:02d}-{int(day):02d}"
            except ValueError:
                continue
        ym = _YEAR_RE.search(window)
        if ym and _MONEY_RE.search(window):
            return f"{ym.group(1)}-01-01"
    return None


def chunk_page(page: dict) -> list[Chunk]:
    if page.get("error") or not page.get("raw_html_path"):
        return []
    html_path = REPO_ROOT / page["raw_html_path"]
    html = html_path.read_text(encoding="utf-8")
    main = load_main(html)
    if main is None:
        return []

    facets = Facets(**page["default_facets"])
    chunks: list[Chunk] = []
    index = 0
    for heading, section_text in split_into_sections(main):
        # Classify once per *section*, not per sub-chunk fragment: a long
        # "Example:"-led section split into pieces by sub_split() would
        # otherwise only get the "example" tag on the piece containing the
        # literal marker, and continuation pieces (same worked example, no
        # marker text of their own) would fall through to a numeric_fact
        # misclassification — confirmed happening before this fix.
        section_content_type = classify_content_type(heading, section_text)
        for piece in sub_split(section_text):
            if len(piece) < MIN_CHUNK_CHARS:
                continue  # boilerplate noise that slipped through stripping, not a real short answer
            content_type = section_content_type
            effective_date = extract_effective_date(piece) if content_type == "numeric_fact" else None
            text = f"{heading}. {piece}" if heading else piece
            chunk = Chunk(
                chunk_id=f"{page['id']}::{index}",
                page_id=page["id"],
                chunk_index=index,
                url=page["url"],
                source_authority=page["source_authority"],
                tier=page["tier"],
                jurisdiction=page["jurisdiction"],
                content_type=content_type,
                facets=facets,
                text=text,
                effective_date=effective_date,
                review_date=None,
            )
            validate_chunk_fields(content_type=chunk.content_type, facets=chunk.facets)
            chunks.append(chunk)
            index += 1
    return chunks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", nargs="*", help="Chunk only these page ids")
    args = parser.parse_args()

    if not MANIFEST_PATH.exists():
        print(f"No manifest at {MANIFEST_PATH} — run fetch.py first.", file=sys.stderr)
        return 1

    all_pages = [json.loads(line) for line in MANIFEST_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    pages = [p for p in all_pages if p["id"] in args.only] if args.only else all_pages

    new_chunks: list[Chunk] = []
    skipped = []
    for page in pages:
        chunks = chunk_page(page)
        if not chunks:
            skipped.append(page["id"])
        new_chunks.extend(chunks)

    if args.only:
        # Merge into existing chunks.jsonl rather than overwriting it with
        # only the filtered pages' output — mirrors fetch.py's --only
        # behaviour. (Bug found the hard way: an earlier version of this
        # script didn't merge, and a --only sanity-check run silently
        # replaced the full 1052-chunk corpus with 15 chunks from one page.)
        by_page: dict[str, list[dict]] = {}
        if CHUNKS_PATH.exists():
            for line in CHUNKS_PATH.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    rec = json.loads(line)
                    by_page.setdefault(rec["page_id"], []).append(rec)
        for pid in args.only:
            by_page[pid] = [c.to_json() for c in new_chunks if c.page_id == pid]
        all_chunks_json = [rec for recs in by_page.values() for rec in recs]
    else:
        all_chunks_json = [c.to_json() for c in new_chunks]

    all_chunks = all_chunks_json

    # Exact-text dedup: CRA repeats a shared glossary block (e.g. "Spouse. A
    # person to whom you are legally married.") verbatim across ~11 TFSA
    # pages — each occurrence is correct content, but indexing it 11 times
    # bloats retrieval with near-duplicate hits for no benefit. Keep the
    # first occurrence only; found on the full 93-page run to be ~16% of
    # all chunks (197 of 1250) before this pass.
    seen_text: set[str] = set()
    deduped: list[dict] = []
    n_dupes = 0
    for c in all_chunks:
        if c["text"] in seen_text:
            n_dupes += 1
            continue
        seen_text.add(c["text"])
        deduped.append(c)
    all_chunks = deduped

    DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    with CHUNKS_PATH.open("w", encoding="utf-8") as f:
        for c in all_chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    print(f"{len(pages)} pages -> {len(all_chunks)} chunks ({n_dupes} exact-duplicate chunks dropped, {len(skipped)} pages produced 0 chunks)")
    if skipped:
        print("  zero-chunk pages:", ", ".join(skipped))
    print(f"Written: {CHUNKS_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
