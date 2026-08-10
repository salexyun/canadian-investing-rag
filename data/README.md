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

93 pages across 12 active authorities (5-pillar scope — see the main
[README's Scope section](../README.md#scope)). The full, authoritative
URL list lives in [ingestion/sources.py](../ingestion/sources.py) —
one entry per page, tagged with facets — not duplicated here as a
second hand-maintained table; at this size that would just reintroduce
the drift risk the schema sanity-check pass eliminated. This table is
the authority-level summary, generated from the actual fetched
manifest (not hand-typed):

| Authority | Tier | Jurisdiction | Fetch method | Pages | License |
|---|---|---|---|---|---|
| CRA (`cra`) | primary | federal | headless browser | 76 | OGL-Canada |
| OSC / GetSmarterAboutMoney (`osc_gsam`) | primary | none | direct HTTP | 3 | OSC content |
| Service Canada / ESDC (`esdc`) | primary | federal | headless browser | 2 | OGL-Canada |
| CIRO (`ciro`) | primary | national | headless browser | 1 | CIRO content |
| AMF (`amf`) | primary | qc | headless browser | 1 | AMF content |
| CIPF (`cipf`) | primary | national | direct HTTP | 2 | CIPF content |
| CDIC (`cdic`) | primary | federal | direct HTTP | 2 | CDIC content |
| TD (`td`) | secondary | none | direct HTTP | 2 | TD content |
| FP Canada (`fpcanada`) | secondary | none | direct HTTP | 1 | FP Canada content |
| MoneySense (`moneysense`) | secondary | none | direct HTTP | 1 | MoneySense content |
| RBC (`rbc`) | secondary | none | direct HTTP | 1 | RBC content |
| Questrade (`questrade`) | secondary | none | direct HTTP | 1 | Questrade content |

## Content-quality audit

A text-length audit after the breadth-expansion pass found ~40% of
pages (26/66 at the time) were "thin" — under 3,000 visible characters
despite ~180KB of raw HTML. Not a fetch failure: a systemic CRA
pattern where a subpage is itself a hub (one intro sentence, then a
"Services and information"/"Topics" link list to the real leaf pages),
not the leaf content. `cra_investment_income` — one of the original 15
sources, from before this rigor was applied — had this too: a
one-sentence overview pointing to the real Line 12000/12100/12700
content we'd never fetched.

Fixed by drilling into each hub's actual link structure (same method
as the original breadth pass — pulled from real fetched HTML, not
guessed) and fetching the real leaf pages: TFSA death/owing-tax/
contributing subpages, FHSA life-events subpages, and — the biggest
find — RRSP was missing the same opening/contributing/transferring/
withdrawing coverage TFSA and FHSA already had, plus RRIF- and
PRPP-specific procedural pages, RESP grant details, and the three
CRA tax-line pages. One page (`cra_rrsp_contributing_prpp`) turned out
to be a hub-under-a-hub; fixed its two highest-value children
(deduction limit, excess contributions) and deliberately **stopped
there** rather than continuing to drill indefinitely — diminishing
returns three levels into CRA's site tree.

Also dropped three sources found to be structurally unfetchable or
low-value during this same audit, rather than left silently degrading
retrieval quality: `gsam_investing_101`/`gsam_investing_102` (the
`academy.getsmarteraboutmoney.ca` subdomain is Cloudflare-blocked for
headless browser and returns a content-free ~1.8KB shell over plain
HTTP — confirmed subdomain-wide when `osc_investing_academy`, fetched
successfully earlier in the same session, later 403'd on a re-run) and
`gsam_etf_101` (video-based, ~950 chars of surrounding text, nothing
to chunk). Replaced with `gsam_stock_market_works`, a genuine ~12K-char
article on the same publisher's other subdomain, verified before
adding rather than assumed.

**Result**: 93 pages, 0 fetch errors, median visible text per page
4,653 characters (up from 4,897 on the pre-audit 66-page set — flat
rather than up, because many of the new leaf pages are legitimately
short single-fact answers, e.g. the spousal-RRSP-at-71 rule is one
real sentence; spot-checked several of the still-under-3,000-char
pages individually to confirm short-and-complete rather than another
hidden hub layer before accepting the number).

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

## Chunking

`ingestion/pipeline.py` reads `data/raw/manifest.jsonl`, chunks each
page's raw HTML, and writes `data/processed/chunks.jsonl` — one
`Chunk` record per line (see Schema above). Strategy and the concrete
bugs it took to get here:

- **Heading-driven splitting, not fixed-size windows** — split at
  h1/h2 boundaries, sub-splitting long sections (~1200 char target,
  sentence-boundary overlap) rather than cutting an arbitrary window
  through a document. This is why it mattered: a fixed-size window
  could easily cut "$7,000... January 1, 2026" in half.
- **Government-template-aware boilerplate stripping** — CRA/ESDC pages
  share the WET-BOEW template, so specific classes (`gc-most-requested`,
  `gc-srvinfo`, `pagedetails`, `alert`) are stripped explicitly, backed
  by a generic link-density heuristic (a block that's mostly `<a>` text
  with 2+ links is navigation, not content) for non-government
  templates. A cookie-consent/language-selector pattern was added after
  it leaked through on CIPF (different template than the government
  pages the explicit classes target).
- **No artificial minimum chunk size** — several genuine leaf pages are
  a single complete sentence (e.g. the spousal-RRSP-at-71 rule); that's
  a precise, good chunk, not something to force-merge. A separate
  40-char floor exists only to catch boilerplate that slipped through
  stripping (breadcrumbs, attribution lines), not to enforce a target
  length — confirmed by checking that every genuine short-but-complete
  chunk found during review was 138+ chars, well clear of that floor.
- **`content_type` decided once per section, not per sub-chunk
  fragment** — found the hard way: CRA pages frequently embed a worked
  example (marked `Example:`, not prose "for example") inside an
  otherwise conceptual/procedural section. Classifying each sub-split
  fragment independently meant only the piece containing the literal
  marker got tagged `example`; continuation pieces of the *same*
  example fell through to `numeric_fact` — and then had years pulled
  from the example's narrative ("Moira... in 2023... in 2025") extracted
  as if they were the current rule's real `effective_date`. Fixed by
  classifying the whole section once and applying it to every
  sub-chunk; `effective_date` extraction is scoped to a window around
  actual limit-language ("dollar limit", "deduction limit"), not any
  date near any dollar amount.
- **Structural bug, not a content bug, caused 25/93 pages to initially
  produce zero chunks** — sibling-walking from each heading tag failed
  silently on pages where CRA wraps each heading in its own
  single-child container div, leaving the real content in a sibling
  container one level up at an inconsistent nesting depth per page.
  Confirmed via a page independently verified to have real content
  (`cra_rrsp_turn71_spousal`) producing zero sections. Fixed by walking
  the document in flattened order and assigning each content block to
  the most recently seen heading, which is robust to nesting depth
  where sibling relationships aren't.
- **Exact-text deduplication** — CRA repeats a shared glossary block
  (e.g. "Spouse. A person to whom you are legally married.") verbatim
  across ~11 TFSA pages. Correct content, but indexing it 11 times
  would bloat retrieval with near-duplicate hits for no benefit — found
  to be 197 of 1250 chunks (~16%) before a dedup pass; final corpus
  keeps the first occurrence only.
- **Facets inherit from the page unmodified** — no per-chunk
  refinement in v1, which is safe specifically because the corpus is
  mostly narrow, single-topic leaf pages after the content-quality
  audit; a page's `default_facets` are already precise at chunk
  granularity.

**Result**: 93 pages -> 1,052 chunks (991 primary / 61 secondary).
Content type: 603 conceptual, 313 example, 74 procedural, 62
numeric_fact. 15 chunks carry a confirmed `effective_date`. 5 pages
produce zero chunks, all confirmed correct: 4 pure-hub CRA pages whose
real content lives in leaf pages fetched separately (see Content-
quality audit), plus `cipf_about`, whose only content turned out to be
the cookie-consent banner once stripped.

## Fetchability summary

Every primary *regulator* (CRA, CIRO, AMF) sits behind bot protection
(Akamai or Cloudflare) even though each `robots.txt` explicitly
permits crawling — plain HTTP clients get an instant block, a real
browser session loads the page cleanly. CIPF and CDIC fetch directly
over plain HTTP despite being just as authoritative — regulator status
doesn't reliably predict bot protection. It also doesn't reliably
predict its *absence*: `academy.getsmarteraboutmoney.ca` (OSC's own
subdomain) turned out to be Cloudflare-protected too — a real "Just a
moment" JS challenge for headless browser, and a content-free shell
for plain HTTP — confirmed subdomain-wide, not one flaky page (see the
Content-quality audit above). Treat each *domain*, not each publisher,
as needing its own fetchability check; a publisher being unprotected
on one subdomain says nothing about another.

- **Headless-browser fetch path**: CRA, ESDC, CIRO, AMF
- **Plain HTTP fetch path**: OSC/GetSmarterAboutMoney (`www.` subdomain
  only), CIPF, CDIC, FP Canada, MoneySense, RBC, TD, Questrade

Add a politeness delay between requests regardless of path, since none
of these sites publish a rate limit. Confirmed at full scale: 93 pages
fetched successfully, 0 fetch errors (one source,
`academy.getsmarteraboutmoney.ca`, was dropped after confirming it
unfetchable via either path — see Content-quality audit).

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
