"""Seed list of pages to ingest.

This is a starting set — one or more pages per source in
data/README.md, enough to exercise both fetch paths and both trust
tiers. Extend it as coverage needs grow — see data/README.md for the
full vetting (legitimacy, appropriateness, fetchability) behind each
entry and why the primary/secondary split and fetch method were
chosen, and ingestion/schema.py for what source_authority,
jurisdiction, and default_topic_tags mean and their allowed values.

Every entry is validated against ingestion/schema.py's controlled
vocabularies at import time — an unregistered authority, an invalid
jurisdiction, or a typo'd tag fails immediately instead of silently
corrupting trust-tiering downstream.
"""

from dataclasses import dataclass

from schema import validate_source_fields


@dataclass(frozen=True)
class Source:
    id: str  # slug — used as the raw HTML filename and manifest key
    url: str
    source_name: str  # human-readable, e.g. "CRA"
    source_authority: str  # normalized slug, e.g. "cra" — see schema.SOURCE_AUTHORITIES
    jurisdiction: str  # see schema.JURISDICTIONS
    tier: str  # "primary" | "secondary"
    fetch_method: str  # "browser" | "http"
    license: str
    topic: str  # human-readable description
    default_topic_tags: tuple[str, ...]  # see schema.TOPIC_TAGS_VOCAB — must include >=1 account-type tag

    def __post_init__(self) -> None:
        validate_source_fields(
            source_authority=self.source_authority,
            jurisdiction=self.jurisdiction,
            tier=self.tier,
            topic_tags=list(self.default_topic_tags),
        )


OGL = "Open Government Licence – Canada"

SOURCES: list[Source] = [
    # --- Primary: CRA (canada.ca) — federal, Akamai-blocked for plain HTTP ---
    Source(
        "cra_tfsa",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/tax-free-savings-account.html",
        "CRA", "cra", "federal", "primary", "browser", OGL,
        "TFSA rules, contribution room, residency",
        ("tfsa", "eligibility", "contribution_room"),
    ),
    Source(
        "cra_fhsa",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/first-home-savings-account.html",
        "CRA", "cra", "federal", "primary", "browser", OGL,
        "FHSA eligibility, contribution limits",
        ("fhsa", "eligibility", "contribution_room"),
    ),
    Source(
        "cra_rrsp",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/rrsps-related-plans.html",
        "CRA", "cra", "federal", "primary", "browser", OGL,
        "RRSP setup, contributions, HBP, RRIF",
        ("rrsp", "eligibility", "contribution_room", "withdrawals"),
    ),
    Source(
        "cra_resp",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/registered-education-savings-plans-resps.html",
        "CRA", "cra", "federal", "primary", "browser", OGL,
        "RESP, CESG, CLB grants",
        ("resp", "eligibility"),
    ),
    Source(
        "cra_investment_income",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/about-your-tax-return/tax-return/completing-a-tax-return/personal-income/investment-income.html",
        "CRA", "cra", "federal", "primary", "browser", OGL,
        "Capital gains / dividend taxation basics",
        ("general_investing", "taxation"),
    ),
    Source(
        "cra_folio_dividends",
        "https://www.canada.ca/en/revenue-agency/services/tax/technical-information/income-tax/income-tax-folios-index/series-3-property-investments-savings-plans/series-3-property-investments-savings-plan-folio-2-dividends/income-tax-folio-s3-f2-c2-taxable-dividends-corporations-resident-canada.html",
        "CRA", "cra", "federal", "primary", "browser", OGL,
        "Technical dividend taxation folio (dense — good for depth)",
        ("general_investing", "taxation"),
    ),

    # --- Primary: CIRO — national SRO, Cloudflare-blocked for plain HTTP ---
    Source(
        "ciro_office_investor",
        "https://www.ciro.ca/office-investor",
        "CIRO", "ciro", "national", "primary", "browser", "CIRO content",
        "Dealer regulation, investor protection, complaints, fraud",
        ("regulatory", "dealer_regulation", "complaints", "fraud_protection"),
    ),

    # --- Primary: AMF — Quebec provincial regulator, WAF-blocked for plain HTTP ---
    Source(
        "amf_general_public",
        "https://lautorite.qc.ca/en/general-public",
        "AMF", "amf", "qc", "primary", "browser", "AMF content",
        "Quebec-specific securities/insurance regulation",
        ("regulatory", "general_investing"),
    ),

    # --- Primary: OSC — Ontario regulator, fetches directly over plain HTTP ---
    Source(
        "osc_gsam_home",
        "https://www.getsmarteraboutmoney.ca/",
        "OSC / GetSmarterAboutMoney", "osc_gsam", "on", "primary", "http", "OSC content",
        "Investing basics hub",
        ("general_investing", "diversification"),
    ),
    Source(
        "osc_investing_academy",
        "https://academy.getsmarteraboutmoney.ca/",
        "OSC / Investing Academy", "osc_gsam", "on", "primary", "http", "OSC content",
        "Structured investing lessons",
        ("general_investing", "diversification"),
    ),

    # --- Secondary: journalism, banks, private entities — no jurisdictional authority ---
    Source(
        "fpcanada_home",
        "https://www.fpcanada.ca/",
        "FP Canada", "fpcanada", "none", "secondary", "http", "FP Canada content",
        "Consumer life-moment financial planning",
        ("general_investing", "practical_howto"),
    ),
    Source(
        "moneysense_home",
        "https://www.moneysense.ca/",
        "MoneySense", "moneysense", "none", "secondary", "http", "MoneySense content",
        "Canadian personal-finance journalism",
        ("general_investing", "practical_howto"),
    ),
    Source(
        "rbc_tfsa",
        "https://www.rbcroyalbank.com/investments/tfsa.html",
        "RBC", "rbc", "none", "secondary", "http", "RBC content",
        "Practical TFSA account-opening steps",
        ("tfsa", "practical_howto"),
    ),
    Source(
        "td_tfsa",
        "https://www.td.com/ca/en/personal-banking/personal-investing/products/investment-plans/tfsa",
        "TD", "td", "none", "secondary", "http", "TD content",
        "Practical TFSA account-opening steps",
        ("tfsa", "practical_howto"),
    ),
    Source(
        "questrade_learning",
        "https://www.questrade.com/learning",
        "Questrade", "questrade", "none", "secondary", "http", "Questrade content",
        "Practical DIY-investing steps",
        ("general_investing", "practical_howto"),
    ),
]
