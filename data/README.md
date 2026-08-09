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

This distinction should be encoded in retrieval/prompting (e.g. a
`source_tier` field on each chunk, with the prompt instructed to
prefer `primary` and to say so explicitly when only `secondary`
content is available).

## Primary sources (government official / government-endorsed)

| Source | URL | Topic | License | Fetch method |
|---|---|---|---|---|
| CRA (canada.ca) | [TFSA](https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/tax-free-savings-account.html) | TFSA rules, contribution room, residency | OGL-Canada | Headless browser (blocked for plain HTTP) |
| CRA (canada.ca) | [FHSA](https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/first-home-savings-account.html) | FHSA eligibility, contribution limits | OGL-Canada | Headless browser |
| CRA (canada.ca) | [RRSPs and related plans](https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/rrsps-related-plans.html) | RRSP setup, contributions, HBP, RRIF | OGL-Canada | Headless browser |
| CRA (canada.ca) | [RESP](https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/registered-education-savings-plans-resps.html) | RESP, CESG, CLB grants | OGL-Canada | Headless browser |
| CRA (canada.ca) | [Investment income](https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/about-your-tax-return/tax-return/completing-a-tax-return/personal-income/investment-income.html) | Capital gains / dividend taxation basics | OGL-Canada | Headless browser |
| CRA (canada.ca) | [Income Tax Folio S3-F2-C2](https://www.canada.ca/en/revenue-agency/services/tax/technical-information/income-tax/income-tax-folios-index/series-3-property-investments-savings-plans/series-3-property-investments-savings-plan-folio-2-dividends/income-tax-folio-s3-f2-c2-taxable-dividends-corporations-resident-canada.html) | Technical dividend taxation (dense — good for depth) | OGL-Canada | Headless browser |
| OSC (Crown agency of Ontario) | [GetSmarterAboutMoney.ca](https://www.getsmarteraboutmoney.ca/) + [Investing Academy](https://academy.getsmarteraboutmoney.ca/) | Structured investing/personal-finance lessons | OSC content | ✅ Direct HTTP — fetches clean |
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
Re-run ingestion for CRA pages at least at each of those windows, and
record the fetch date per document so retrieval can surface "as of"
context rather than silently serving stale numbers.
