# Data

`raw/` and `processed/` are gitignored (populated by the ingestion
pipeline, not committed) — see [ingestion/](../ingestion/) and
[docs/setup.md](../docs/setup.md).

All sources below were verified 2026-08-09: checked `robots.txt`,
test-fetched with a plain HTTP client (`curl`), and — where that
failed — confirmed the page still loads and is legitimate via a real
browser session.

## Source tiering

Sources are split into two trust tiers, and the split is load-bearing,
not cosmetic:

- **Primary** — government official, or an entity a government has
  legislated/mandated as the authority (a Crown agency or a national
  self-regulatory organization recognized by the provincial securities
  regulators). These are the only sources allowed to back **numeric
  facts and eligibility rules** (contribution limits, deadlines,
  residency requirements).
- **Secondary** — journalism, banks, and other private entities.
  Useful for practical/explanatory framing, **never used to answer a
  rules or numbers question on their own**, and always presented as
  lower-authority than a primary source if the two ever disagree.

This distinction is encoded in the schema below (`tier` on every page
and chunk), with the prompt instructed to prefer `primary` and to say
so explicitly when only `secondary` content is available.

## Schema

Two layers, defined in [ingestion/schema.py](../ingestion/schema.py) —
deliberately not one flat schema, because trust/freshness/topic
metadata varies *within* a page in ways a page-level record can't
capture. A CRA TFSA page's contribution-limit sentence is a
`numeric_fact` with a real `effective_date`; the same page's "what is
a TFSA" paragraph is `conceptual` and evergreen. Two different chunks,
same page — so that metadata has to live on the chunk, not the page.

Every field below earns its place by driving one of: retrieval
filtering, trust/freshness behaviour in the prompt, or citation
display. A sanity pass (below) removed one that didn't.

**Page** (`FetchedPage`, written today by `ingestion/fetch.py` to
`data/raw/manifest.jsonl`) — provenance and source-authority context:
`id`, `url`, `source_name`, `source_authority` (normalized slug, e.g.
`cra`), `jurisdiction` (`federal | national | on | qc | bc | none`),
`tier` (`primary | secondary`), `fetch_method`, `license`, `topic`,
`default_facets`, `fetched_at`, `page_last_updated` (best-effort, from
the page's own `dcterms.modified` metadata where present),
`content_hash` (sha256 — lets a re-run detect "this page didn't
actually change"), plus `http_status` / `title` / `raw_html_path` /
`content_length` / `error` (fetch-operational diagnostics — correctly
*not* propagated to Chunk, since they don't mean anything at retrieval
time).

`source_name` / `tier` / `license` / `fetch_method` are looked up from
a single registry (`SOURCE_AUTHORITY_INFO`, keyed by
`source_authority`) rather than typed per page — verified that every
page from a given authority always carries the same values, so
hand-typing them per source was pure redundancy and a drift risk.
`jurisdiction` is the one field with a registry *default* that a page
can override, since it means "what this content applies to" and that
can genuinely differ from the publisher's usual scope (see the
osc_gsam fix below).

**Chunk** (`Chunk`, drafted now, written once `ingestion/pipeline.py`
exists) — one per retrievable unit, several per page. Inherits
`url` / `source_authority` / `tier` / `jurisdiction` from its parent
page rather than re-deriving them, then adds what's genuinely
per-chunk: `content_type` (`conceptual | numeric_fact | procedural |
example`), `facets` (starts as the page's `default_facets`, refined
per chunk), `effective_date` (when this fact became true — not the
same as `page_last_updated`, which is when the *page* was last
edited), and `review_date` (when *we* last confirmed the chunk is
still accurate).

`jurisdiction` keeps `national` distinct from `federal` on purpose:
CIRO is a self-regulatory body recognized by provincial securities
commissions, not a federal government department — collapsing that
into "federal" would misrepresent how Canadian securities regulation
actually works.

### Facets

Five dimensions, not one flat tag bag — a chunk about "withdrawing
from a TFSA" and a chunk about "the dividend tax credit on
non-registered investments" have nothing in common except both being
investing content, and forcing them into the same tag vocabulary loses
the ability to filter cleanly (e.g. "every `numeric_fact` chunk about
`rrsp` + `withdrawing` + `non_resident`"):

- **`account_type`** — required, single-valued, closed by construction
  (Canada has exactly these registered-account types): `tfsa | rrsp |
  rrif | fhsa | resp | rdsp | lira_lrsp | prpp | non_registered | none`
- **`tax_concepts`** — bounded, multi-valued: `capital_gains |
  capital_losses | superficial_loss | attribution_rules |
  contribution_room | over_contribution_penalty | withholding_tax |
  tax_deduction | tax_credit | dividend_tax_credit | oas_clawback`
- **`investment_vehicles`** — bounded, multi-valued: `stocks | etfs |
  mutual_funds | bonds | gics | reits | options | crypto`
- **`actions`** — bounded, multi-valued: `contributing | withdrawing |
  transferring | opening_account | filing_taxes | calculating_room`
- **`special_situations`** — bounded, multi-valued: `death_and_estates
  | divorce_separation | non_resident`. Elevated to its own facet
  rather than left as a generic tag: this project's whole premise is
  that residency/life-event status changes the answer, so it needs to
  be filterable on its own, not buried.

Not every page fits these five — CIRO/AMF/CIPF/CDIC/OSC-GSAM content is
institutional/educational/regulatory, not about a specific account+
tax+vehicle+action. Those get `account_type="none"` and retrieval
leans on `source_authority`/`topic` instead; that's an accepted gap,
not an oversight, since the facets exist to make the core
account-and-instrument content filterable, not to force-fit
everything.

Every source is validated against these vocabularies (plus
`SOURCE_AUTHORITY_INFO`, `JURISDICTIONS`, `CONTENT_TYPES`) at
registration time via `validate_source_fields` / `validate_chunk_fields`
— an unregistered authority, an invalid jurisdiction, or a typo'd facet
value raises immediately rather than silently reaching the knowledge
base.

**Coverage gaps found by this schema, not by eyeballing:** the
original 15-source pass showed zero coverage for `rdsp` and
`lira_lrsp`, and `rrif` only folded into the RRSP page. All three
closed in the breadth-expansion pass below — `rrif` and `rdsp` got
dedicated primary CRA pages; `lira_lrsp` did not (see "Known gap"
below, it stayed a gap on purpose rather than being papered over).
That same pass also surfaced `prpp` (Pooled Registered Pension Plan) —
a real Canadian registered-account type missing from the original
`ACCOUNT_TYPES` set entirely — while pulling RRSP subpages; added, since
the facet claims to be exhaustive of Canada's account types and wasn't.

### Sanity-check pass (removed / fixed on review)

Nothing here proved out to be needed on its own justification — each
of these was checked against "does it improve retrieval, or does it
make what's retrieved more useful," not kept by default:

- **Dropped `page_issued`.** It answered "when was this URL first
  published," which drives no retrieval, trust, or freshness decision
  — that's `page_last_updated`/`content_hash` (page changed?) and
  `Chunk.effective_date` (when did *this fact* become true?), which
  page-creation-date duplicates neither of.
- **Fixed `jurisdiction` conflating publisher with applicability.**
  OSC/GetSmarterAboutMoney was tagged `on` because OSC is Ontario's
  regulator — but the actual content (investing basics, diversification)
  isn't Ontario-specific. Left as `on`, a jurisdiction filter could
  wrongly exclude it for a BC/Quebec user. Now defaults to `none`
  (applies nationally) via the registry.
- **Collapsed real redundancy into one registry.** Checked whether
  `source_name`/`tier`/`license`/`fetch_method` ever varied within a
  `source_authority` across the fetched manifest — they didn't, in any
  of the 15 pages. Hand-typing four fixed-per-publisher values on every
  `Source(...)` call was drift risk with no benefit, so
  `SOURCE_AUTHORITY_INFO` + `make_source()` now derive them from one
  place. (The similar-looking duplication *within* `Chunk` — carrying
  `url`/`source_authority`/`tier`/`jurisdiction` on every chunk — was
  kept: that's denormalization for query-time performance, a chunk
  needs to be self-contained at retrieval time, which is a different
  justification than "typed the same string 15 times by hand.")
- **Kept, after consideration:** `topic` (free text) overlaps somewhat
  with the structured facets, but serves a different audience — a
  human skimming `sources.py` — and costs one string field, so it
  stayed. `content_length`/`http_status` are diagnostic-only, not
  retrieval-relevant, but near-zero cost and useful for debugging a
  failed fetch, so they stayed too.

## Sources

66 pages across 12 active authorities (5-pillar scope — see the main
[README's Scope section](../README.md#scope)). The full, authoritative
URL list lives in [ingestion/sources.py](../ingestion/sources.py) —
one entry per page, tagged with facets — not duplicated here as a
second hand-maintained table; at this size that would just reintroduce
the drift risk the schema sanity-check pass eliminated. This table is
the authority-level summary, generated from the actual fetched
manifest (not hand-typed):

| Authority | Tier | Jurisdiction | Fetch method | Pages | License |
|---|---|---|---|---|---|
| CRA (`cra`) | primary | federal | headless browser | 48 | OGL-Canada |
| OSC / GetSmarterAboutMoney (`osc_gsam`) | primary | none | direct HTTP | 6 | OSC content |
| Service Canada / ESDC (`esdc`) | primary | federal | headless browser | 2 | OGL-Canada |
| CIRO (`ciro`) | primary | national | headless browser | 1 | CIRO content |
| AMF (`amf`) | primary | qc | headless browser | 1 | AMF content |
| CIPF (`cipf`) | primary | national | direct HTTP | 1 | CIPF content |
| CDIC (`cdic`) | primary | federal | direct HTTP | 1 | CDIC content |
| TD (`td`) | secondary | none | direct HTTP | 2 | TD content |
| FP Canada (`fpcanada`) | secondary | none | direct HTTP | 1 | FP Canada content |
| MoneySense (`moneysense`) | secondary | none | direct HTTP | 1 | MoneySense content |
| RBC (`rbc`) | secondary | none | direct HTTP | 1 | RBC content |
| Questrade (`questrade`) | secondary | none | direct HTTP | 1 | Questrade content |

CIPF/CDIC are industry-funded but classed **primary**, not secondary
— coverage is a CIRO-membership requirement (CIPF) or a federal Crown
corporation (CDIC), a mandated protection scheme rather than a
commercial explainer with a product to sell. Same reasoning as CIRO.

Secondary sources are supplementary only — practical "how do I
actually do this" framing, never authoritative for rules or numbers.
Bank sources in particular have a direct commercial incentive (each is
explaining the account type it also sells). TD additionally publishes
an `LLMS.txt` (`td.com/LLMS.txt`) with AI-crawler guidance; read it
before scraping further TD pages.

**Known gap, left open rather than papered over:** no clean primary
(CRA) consumer page exists for LIRA/LRSP — they're governed by
provincial pension-standards legislation layered on federal RRSP tax
rules, more fragmented than the other account types. The only source
found is TD's explainer (secondary tier). This is a real gap in
primary-source coverage for that account type, not a settled matter.

**Registered but not yet integrated:** `boc` (Bank of Canada) is in
the authority registry with 0 pages — its Valet API returns JSON, a
different shape than this HTML-fetch pipeline, and is deliberately
deferred to a small separate integration rather than forced through
`fetch.py`.

**Considered and excluded, not just unhandled:**

- **BCFSA / FSRA (Ontario)** — official provincial regulators, but
  their remit (insurance/mortgage) is explicitly out of scope per the
  main README's Scope section.
- **StatCan** — official and fetchable, but survey/statistical tables,
  not Q&A-shaped prose. Better suited to a future monitoring-dashboard
  stat than the retrieval corpus.
- **open.canada.ca** — only worth pulling if a specific tax/investment
  dataset turns up; none found yet.
- **Pre-built HuggingFace/Kaggle Q&A datasets** — searched, found
  nothing suitable for this niche. Confirms the corpus needs to be
  built from these sources directly.

## Fetchability summary

Every primary *regulator* (CRA, CIRO, AMF) sits behind bot protection
(Akamai or Cloudflare) even though each `robots.txt` explicitly
permits crawling — plain HTTP clients get an instant block, a real
browser session loads the page cleanly. Every other source tested —
including the two newer primary additions, CIPF and CDIC — fetches
directly over plain HTTP; regulator status doesn't predict bot
protection (CIPF/CDIC are as authoritative as CIRO but unprotected).

- **Headless-browser fetch path**: CRA, ESDC, CIRO, AMF
- **Plain HTTP fetch path**: OSC/GetSmarterAboutMoney, CIPF, CDIC, FP
  Canada, MoneySense, RBC, TD, Questrade

No JS challenge/CAPTCHA was observed on any source (Cloudflare's
"Just a moment" interstitial cleared automatically in a normal browser
session), so headless Chromium is sufficient without a CAPTCHA-solving
step — add a politeness delay between requests regardless, since none
of these sites publish a rate limit. Confirmed at full scale: all 66
pages fetched successfully in one run, 0 failures.

## Freshness

CRA contribution limits and thresholds change on a predictable cycle
(new limits announced in the fall, tax bracket changes each January).
Re-run ingestion for CRA pages at least at each of those windows.

Two distinct dates now track this per chunk, and they answer different
questions: `effective_date` is when a fact became true in the real
world (e.g. the 2026 TFSA limit takes effect 2026-01-01, regardless of
when CRA edited the page); `review_date` is when *we* last confirmed
the chunk is still accurate. `page_last_updated` and `content_hash`
(both page level) support this from the fetch side — a re-run that
finds an unchanged hash needs no re-review; a changed hash on a page
whose chunks include `numeric_fact` entries should trigger one before
those chunks are trusted again.
