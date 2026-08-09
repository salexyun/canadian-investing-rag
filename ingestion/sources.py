"""Seed list of pages to ingest.

This is a starting set — one or more pages per source in
data/README.md, enough to exercise both fetch paths and both trust
tiers. Extend it as chunking/coverage needs grow; see
data/README.md for the full vetting (legitimacy, appropriateness,
fetchability) behind each entry and why the primary/secondary split
and fetch method were chosen.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Source:
    id: str  # slug — used as the raw HTML filename and manifest key
    url: str
    source_name: str
    tier: str  # "primary" | "secondary"
    fetch_method: str  # "browser" | "http"
    license: str
    topic: str


OGL = "Open Government Licence – Canada"

SOURCES: list[Source] = [
    # --- Primary: CRA (canada.ca) — Akamai-blocked for plain HTTP, needs headless browser ---
    Source(
        "cra_tfsa",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/tax-free-savings-account.html",
        "CRA", "primary", "browser", OGL,
        "TFSA rules, contribution room, residency",
    ),
    Source(
        "cra_fhsa",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/first-home-savings-account.html",
        "CRA", "primary", "browser", OGL,
        "FHSA eligibility, contribution limits",
    ),
    Source(
        "cra_rrsp",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/rrsps-related-plans.html",
        "CRA", "primary", "browser", OGL,
        "RRSP setup, contributions, HBP, RRIF",
    ),
    Source(
        "cra_resp",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/registered-education-savings-plans-resps.html",
        "CRA", "primary", "browser", OGL,
        "RESP, CESG, CLB grants",
    ),
    Source(
        "cra_investment_income",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/about-your-tax-return/tax-return/completing-a-tax-return/personal-income/investment-income.html",
        "CRA", "primary", "browser", OGL,
        "Capital gains / dividend taxation basics",
    ),
    Source(
        "cra_folio_dividends",
        "https://www.canada.ca/en/revenue-agency/services/tax/technical-information/income-tax/income-tax-folios-index/series-3-property-investments-savings-plans/series-3-property-investments-savings-plan-folio-2-dividends/income-tax-folio-s3-f2-c2-taxable-dividends-corporations-resident-canada.html",
        "CRA", "primary", "browser", OGL,
        "Technical dividend taxation folio (dense — good for depth)",
    ),

    # --- Primary: CIRO / AMF — Cloudflare/WAF-blocked for plain HTTP, needs headless browser ---
    Source(
        "ciro_office_investor",
        "https://www.ciro.ca/office-investor",
        "CIRO", "primary", "browser", "CIRO content",
        "Dealer regulation, investor protection, complaints, fraud",
    ),
    Source(
        "amf_general_public",
        "https://lautorite.qc.ca/en/general-public",
        "AMF", "primary", "browser", "AMF content",
        "Quebec-specific securities/insurance regulation",
    ),

    # --- Primary: OSC — fetches directly over plain HTTP ---
    Source(
        "osc_gsam_home",
        "https://www.getsmarteraboutmoney.ca/",
        "OSC / GetSmarterAboutMoney", "primary", "http", "OSC content",
        "Investing basics hub",
    ),
    Source(
        "osc_investing_academy",
        "https://academy.getsmarteraboutmoney.ca/",
        "OSC / Investing Academy", "primary", "http", "OSC content",
        "Structured investing lessons",
    ),

    # --- Secondary: journalism, banks, private entities — plain HTTP, supplementary only ---
    Source(
        "fpcanada_home",
        "https://www.fpcanada.ca/",
        "FP Canada", "secondary", "http", "FP Canada content",
        "Consumer life-moment financial planning",
    ),
    Source(
        "moneysense_home",
        "https://www.moneysense.ca/",
        "MoneySense", "secondary", "http", "MoneySense content",
        "Canadian personal-finance journalism",
    ),
    Source(
        "rbc_tfsa",
        "https://www.rbcroyalbank.com/investments/tfsa.html",
        "RBC", "secondary", "http", "RBC content",
        "Practical TFSA account-opening steps",
    ),
    Source(
        "td_tfsa",
        "https://www.td.com/ca/en/personal-banking/personal-investing/products/investment-plans/tfsa",
        "TD", "secondary", "http", "TD content",
        "Practical TFSA account-opening steps",
    ),
    Source(
        "questrade_learning",
        "https://www.questrade.com/learning",
        "Questrade", "secondary", "http", "Questrade content",
        "Practical DIY-investing steps",
    ),
]
