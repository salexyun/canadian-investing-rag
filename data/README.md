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
  rrif | fhsa | resp | rdsp | lira_lrsp | non_registered | none`
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

Not every page fits these five — CIRO/AMF/OSC-GSAM content is
institutional/educational, not about a specific account+tax+vehicle+
action. Those get `account_type="none"` and retrieval leans on
`source_authority`/`topic` instead; that's an accepted gap, not an
oversight, since the facets exist to make the core registered-account
fact content filterable, not to force-fit everything.

Every source is validated against these vocabularies (plus
`SOURCE_AUTHORITY_INFO`, `JURISDICTIONS`, `CONTENT_TYPES`) at
registration time via `validate_source_fields` / `validate_chunk_fields`
— an unregistered authority, an invalid jurisdiction, or a typo'd facet
value raises immediately rather than silently reaching the knowledge
base.

**Coverage gap found by this schema, not by eyeballing:** running the
15 current sources against the closed `account_type` set shows zero
coverage for `rdsp` and `lira_lrsp`, and `rrif` only appears folded
into the RRSP page rather than as its own account type. Worth filling
when we expand breadth.

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

## Primary sources (government official / government-endorsed)

| Source | URL | Topic | License | Fetch method |
|---|---|---|---|---|
| CRA (canada.ca) | [TFSA](https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/tax-free-savings-account.html) | TFSA rules, contribution room, residency | OGL-Canada | Headless browser (blocked for plain HTTP) |
| CRA (canada.ca) | [FHSA](https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/first-home-savings-account.html) | FHSA eligibility, contribution limits | OGL-Canada | Headless browser |
| CRA (canada.ca) | [RRSPs and related plans](https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/rrsps-related-plans.html) | RRSP setup, contributions, HBP, RRIF | OGL-Canada | Headless browser |
| CRA (canada.ca) | [RESP](https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/registered-education-savings-plans-resps.html) | RESP, CESG, CLB grants | OGL-Canada | Headless browser |
| CRA (canada.ca) | [Investment income](https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/about-your-tax-return/tax-return/completing-a-tax-return/personal-income/investment-income.html) | Capital gains / dividend taxation basics | OGL-Canada | Headless browser |
| CRA (canada.ca) | [Income Tax Folio S3-F2-C2](https://www.canada.ca/en/revenue-agency/services/tax/technical-information/income-tax/income-tax-folios-index/series-3-property-investments-savings-plans/series-3-property-investments-savings-plan-folio-2-dividends/income-tax-folio-s3-f2-c2-taxable-dividends-corporations-resident-canada.html) | Technical dividend taxation (dense — good for depth) | OGL-Canada | Headless browser |
| OSC (Crown agency of Ontario) | [GetSmarterAboutMoney.ca](https://www.getsmarteraboutmoney.ca/) + [Investing Academy](https://academy.getsmarteraboutmoney.ca/) | Structured investing/personal-finance lessons | OSC content | ✅ Direct HTTP — fetches clean (`jurisdiction=none`: general education, not Ontario-specific — see schema notes) |
| CIRO (national SRO, recognized by the CSA) | [Office of the Investor](https://www.ciro.ca/office-investor) | Dealer regulation, investor protection, complaints, fraud | CIRO content | Headless browser (Cloudflare JS challenge blocks plain HTTP) |
| AMF (Government of Quebec) | [General public](https://lautorite.qc.ca/en/general-public) | Quebec-specific securities/insurance regulation | AMF content | Headless browser (WAF blocks plain HTTP) |
| Bank of Canada (Crown corporation) | [Valet API](https://www.bankofcanada.ca/valet/docs) | Interest rates, FX, inflation — macro context | Bank of Canada terms of use | ✅ Direct HTTP — JSON API, no key required |
| Government of Canada Open Data Portal | [search.open.canada.ca](https://search.open.canada.ca/opendata/) | Bulk datasets — pull in only if a specific tax/investment-relevant dataset is found | OGL-Canada | ✅ Direct HTTP (one redirect) |

## Secondary sources (journalism, banks, private entities)

Supplementary only — practical "how do I actually do this" framing,
never authoritative for rules or numbers. Bank sources in particular
have a direct commercial incentive (each is explaining the account
type it also sells), so they're tagged with the issuing institution in
metadata and the prompt should treat them accordingly.

| Source | URL | Topic | Fetch method |
|---|---|---|---|
| FP Canada (private nonprofit, CFP-certifying body) | [fpcanada.ca](https://www.fpcanada.ca/) | Consumer "life moment" financial-planning content | ✅ Direct HTTP |
| MoneySense (commercial media) | [moneysense.ca](https://www.moneysense.ca/) | Canadian personal-finance journalism, FAQ-style | ✅ Direct HTTP |
| RBC (bank, commercial) | [TFSA page](https://www.rbcroyalbank.com/investments/tfsa.html) | Practical account-opening steps | ✅ Direct HTTP |
| TD (bank, commercial) | [TFSA page](https://www.td.com/ca/en/personal-banking/personal-investing/products/investment-plans/tfsa) | Practical account-opening steps | ✅ Direct HTTP — note: TD publishes an `LLMS.txt` (`td.com/LLMS.txt`) with AI-crawler guidance; read it before scraping |
| Questrade (brokerage, commercial) | [Learning centre](https://www.questrade.com/learning) | Practical DIY-investing steps | ✅ Direct HTTP |

## Considered and excluded (for now)

- **BCFSA / FSRA (Ontario)** — official provincial regulators, but
  their remit is insurance/mortgage, outside this project's
  registered-accounts scope. Revisit only if the project scope
  expands.
- **StatCan** — official and fetchable, but its content is survey/
  statistical tables, not Q&A-shaped prose. Better suited to a future
  monitoring-dashboard stat than to the retrieval corpus.
- **Pre-built HuggingFace/Kaggle Q&A datasets** — searched, found
  nothing suitable for this niche. Confirms the corpus needs to be
  built from these sources directly.

## Fetchability summary

Every primary regulator (CRA, CIRO, AMF) sits behind bot protection
(Akamai or Cloudflare) even though each `robots.txt` explicitly
permits crawling — plain HTTP clients get an instant block, a real
browser session loads the page cleanly. Every other source tested
fetches directly over plain HTTP. Practical implication for
`ingestion/`:

- **Headless-browser fetch path** (e.g. Playwright) for: CRA, CIRO, AMF
- **Plain HTTP fetch path** for: OSC/GetSmarterAboutMoney, Bank of
  Canada, open.canada.ca, FP Canada, MoneySense, RBC, TD, Questrade

No JS challenge/CAPTCHA was observed on any source (Cloudflare's
"Just a moment" interstitial cleared automatically in a normal browser
session), so headless Chromium should be sufficient without a
CAPTCHA-solving step — add a politeness delay between requests
regardless, since none of these sites publish a rate limit.

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
