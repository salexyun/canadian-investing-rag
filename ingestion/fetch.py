"""Fetch step of the ingestion pipeline.

Pulls raw HTML for every entry in ``sources.SOURCES`` and writes:

- ``data/raw/<tier>/<id>.html``     — the raw page
- ``data/raw/manifest.jsonl``       — one FetchedPage JSON record per page

Two fetch paths, per source (see data/README.md for why):

- ``browser``: CRA, CIRO, AMF sit behind bot protection (Akamai /
  Cloudflare) that blocks plain HTTP clients outright. Fetched with a
  headless Chromium session via Playwright.
- ``http``:    everything else fetches cleanly with a plain,
  self-identifying HTTP client.

This is deliberately just the *fetch* step — raw HTML in, manifest
out. Chunking and loading into the knowledge base are separate stages
(``ingestion/chunk.py``, ``ingestion/load_vector_store.py``) that read
this manifest.

Usage:
    python ingestion/fetch.py
    python ingestion/fetch.py --only cra_tfsa cra_fhsa
    python ingestion/fetch.py --tier primary
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from schema import FetchedPage
from sources import SOURCES, Source

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_RAW = REPO_ROOT / "data" / "raw"
MANIFEST_PATH = DATA_RAW / "manifest.jsonl"

# Self-identifying UA — every source here has a robots.txt that allows
# "User-agent: *", so there's no reason to impersonate a browser for
# the plain-HTTP path. Confirmed working against all `http`-path
# sources during source vetting (see data/README.md).
HTTP_USER_AGENT = (
    "Mozilla/5.0 (compatible; CanadianInvestingRAG-Bot/0.1; "
    "educational project; +mailto:s.alex.yun@gmail.com)"
)

REQUEST_TIMEOUT_S = 20
POLITENESS_DELAY_S = 1.5  # between requests, per fetch path — none of these sites publish a rate limit


def fetch_via_http(source: Source) -> tuple[str | None, int | None, str | None]:
    """Returns (html, http_status, error)."""
    try:
        resp = requests.get(
            source.url,
            headers={"User-Agent": HTTP_USER_AGENT, "Accept-Language": "en-CA,en;q=0.9"},
            timeout=REQUEST_TIMEOUT_S,
        )
        resp.raise_for_status()
        return resp.text, resp.status_code, None
    except requests.RequestException as e:
        status = getattr(e.response, "status_code", None)
        return None, status, str(e)


def fetch_via_browser(source: Source, browser) -> tuple[str | None, int | None, str | None]:
    """Returns (html, http_status, error). `browser` is a live Playwright browser instance."""
    try:
        page = browser.new_page(user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        ))
        response = page.goto(source.url, wait_until="networkidle", timeout=30_000)
        status = response.status if response else None
        html = page.content()
        page.close()
        return html, status, None
    except Exception as e:  # noqa: BLE001 — surface any Playwright failure as a fetch error
        return None, None, str(e)


def extract_title(html: str) -> str | None:
    soup = BeautifulSoup(html, "lxml")
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    return None


_DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")


def extract_last_updated(html: str) -> str | None:
    """Best-effort extraction of a page's self-reported last-modified date.

    Government of Canada pages (canada.ca — CRA included) expose this
    via a standard <meta name="dcterms.modified"> tag, far more
    reliable than scraping the "Page details" footer widget. Other
    sites vary; we fall back to <time property="dateModified">, then
    any <time datetime="...">, then give up rather than guess.

    (dcterms.issued — original publish date — was considered and
    dropped: it doesn't drive any retrieval, trust, or freshness
    behaviour. What matters is whether the page changed (content_hash,
    page_last_updated) and when a specific fact took effect
    (Chunk.effective_date) — "when was this URL first created" answers
    neither question.)
    """
    soup = BeautifulSoup(html, "lxml")

    meta_tag = soup.find("meta", attrs={"name": "dcterms.modified"})
    if meta_tag and meta_tag.get("content"):
        m = _DATE_RE.search(meta_tag["content"])
        if m:
            return m.group(0)

    time_tag = soup.find("time", attrs={"property": "dateModified"})
    if time_tag and time_tag.get("datetime"):
        m = _DATE_RE.search(time_tag["datetime"])
        if m:
            return m.group(0)

    time_tag = soup.find("time")
    if time_tag:
        candidate = time_tag.get("datetime") or time_tag.get_text()
        m = _DATE_RE.search(candidate)
        if m:
            return m.group(0)

    return None


def fetch_one(source: Source, browser) -> FetchedPage:
    fetched_at = datetime.now(timezone.utc).isoformat()

    if source.fetch_method == "browser":
        html, status, error = fetch_via_browser(source, browser)
    else:
        html, status, error = fetch_via_http(source)

    common = dict(
        id=source.id, url=source.url, source_name=source.source_name,
        source_authority=source.source_authority, jurisdiction=source.jurisdiction,
        tier=source.tier, fetch_method=source.fetch_method, license=source.license,
        topic=source.topic, default_facets=source.default_facets,
        fetched_at=fetched_at,
    )

    if html is None:
        return FetchedPage(
            **common,
            page_last_updated=None, content_hash=None,
            http_status=status, title=None, raw_html_path=None, content_length=0,
            error=error,
        )

    out_dir = DATA_RAW / source.tier
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{source.id}.html"
    out_path.write_text(html, encoding="utf-8")

    return FetchedPage(
        **common,
        page_last_updated=extract_last_updated(html),
        content_hash=hashlib.sha256(html.encode("utf-8")).hexdigest(),
        http_status=status, title=extract_title(html),
        raw_html_path=str(out_path.relative_to(REPO_ROOT)),
        content_length=len(html),
        error=None,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", nargs="*", help="Fetch only these source ids")
    parser.add_argument("--tier", choices=["primary", "secondary"], help="Fetch only this tier")
    args = parser.parse_args()

    sources = SOURCES
    if args.only:
        sources = [s for s in sources if s.id in args.only]
    if args.tier:
        sources = [s for s in sources if s.tier == args.tier]

    if not sources:
        print("No sources matched the given filters.", file=sys.stderr)
        return 1

    needs_browser = any(s.fetch_method == "browser" for s in sources)
    browser_ctx = None
    playwright_ctx = None

    results: list[FetchedPage] = []

    if needs_browser:
        from playwright.sync_api import sync_playwright

        playwright_ctx = sync_playwright().start()
        browser_ctx = playwright_ctx.chromium.launch()

    try:
        for source in sources:
            print(f"Fetching [{source.tier}/{source.fetch_method}] {source.id} ...", end=" ", flush=True)
            result = fetch_one(source, browser_ctx)
            results.append(result)
            status = "OK" if result.error is None else f"FAILED: {result.error}"
            print(status)
            time.sleep(POLITENESS_DELAY_S)
    finally:
        if browser_ctx:
            browser_ctx.close()
        if playwright_ctx:
            playwright_ctx.stop()

    # Rebuild the manifest fresh each run — this is a full re-fetch,
    # not an incremental append. Merge with untouched prior entries
    # when filtering to a subset so `--only` doesn't wipe the rest.
    DATA_RAW.mkdir(parents=True, exist_ok=True)
    existing: dict[str, dict] = {}
    if MANIFEST_PATH.exists():
        for line in MANIFEST_PATH.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                existing[rec["id"]] = rec

    for r in results:
        existing[r.id] = r.to_json()

    with MANIFEST_PATH.open("w", encoding="utf-8") as f:
        for rec in existing.values():
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    n_ok = sum(1 for r in results if r.error is None)
    n_failed = len(results) - n_ok
    print(f"\n{n_ok} succeeded, {n_failed} failed. Manifest: {MANIFEST_PATH.relative_to(REPO_ROOT)}")
    return 1 if n_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
