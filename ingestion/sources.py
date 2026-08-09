"""Seed list of pages to ingest.

This is a starting set — one or more pages per source in
data/README.md, enough to exercise both fetch paths and both trust
tiers. Extend it as coverage needs grow — see data/README.md for the
full vetting (legitimacy, appropriateness, fetchability) behind each
entry, and ingestion/schema.py for what source_authority, jurisdiction,
and the facets mean and their allowed values.

Every entry is validated against ingestion/schema.py's controlled
vocabularies at import time — an unregistered authority, an invalid
jurisdiction, or a typo'd facet value fails immediately instead of
silently corrupting trust-tiering downstream.

Coverage note: tagging these against the closed ACCOUNT_TYPES set
surfaces a real gap — nothing here touches RDSP or LIRA/LRSP, and RRIF
only appears folded into the RRSP page rather than as its own account
type. Worth filling when we expand breadth.
"""

from dataclasses import dataclass

from schema import Facets, SOURCE_AUTHORITY_INFO, validate_source_fields


@dataclass(frozen=True)
class Source:
    id: str  # slug — used as the raw HTML filename and manifest key
    url: str
    source_name: str  # human-readable, e.g. "CRA" — derived, see make_source()
    source_authority: str  # normalized slug, e.g. "cra" — see schema.SOURCE_AUTHORITY_INFO
    jurisdiction: str  # see schema.JURISDICTIONS
    tier: str  # "primary" | "secondary" — derived, see make_source()
    fetch_method: str  # "browser" | "http" — derived, see make_source()
    license: str  # derived, see make_source()
    topic: str  # human-readable description
    default_facets: Facets  # see schema.Facets and its vocabularies

    def __post_init__(self) -> None:
        validate_source_fields(
            source_authority=self.source_authority,
            jurisdiction=self.jurisdiction,
            tier=self.tier,
            facets=self.default_facets,
        )


def make_source(id: str, url: str, source_authority: str, topic: str,
                 facets: Facets, jurisdiction: str | None = None) -> Source:
    """Build a Source, deriving source_name/tier/license/fetch_method from
    SOURCE_AUTHORITY_INFO instead of making every call site retype them.

    Those four are fixed properties of the *publisher*, not the page —
    every page from a given authority has always carried the same
    values (verified against the fetched manifest) — so hand-typing
    them per source was pure redundancy and a drift risk as the source
    list grows. `jurisdiction` is the one exception: it means "what
    this content applies to," which can occasionally differ from a
    publisher's default (pass an override when it does).
    """
    if source_authority not in SOURCE_AUTHORITY_INFO:
        raise ValueError(
            f"Unregistered source_authority {source_authority!r} — add it to "
            f"SOURCE_AUTHORITY_INFO in ingestion/schema.py first."
        )
    info = SOURCE_AUTHORITY_INFO[source_authority]
    return Source(
        id=id, url=url,
        source_name=info["source_name"],
        source_authority=source_authority,
        jurisdiction=jurisdiction if jurisdiction is not None else info["jurisdiction"],
        tier=info["tier"],
        fetch_method=info["fetch_method"],
        license=info["license"],
        topic=topic,
        default_facets=facets,
    )


SOURCES: list[Source] = [
    # --- Primary: CRA (canada.ca) — federal, Akamai-blocked for plain HTTP ---
    make_source(
        "cra_tfsa",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/tax-free-savings-account.html",
        "cra", "TFSA rules, contribution room, residency",
        Facets("tfsa",
               tax_concepts=("contribution_room", "over_contribution_penalty"),
               actions=("contributing", "calculating_room"),
               special_situations=("non_resident",)),
    ),
    make_source(
        "cra_fhsa",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/first-home-savings-account.html",
        "cra", "FHSA eligibility, contribution limits",
        Facets("fhsa",
               tax_concepts=("contribution_room", "tax_deduction"),
               actions=("contributing", "opening_account")),
    ),
    make_source(
        "cra_rrsp",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/rrsps-related-plans.html",
        "cra", "RRSP setup, contributions, HBP, RRIF",
        Facets("rrsp",
               tax_concepts=("contribution_room", "tax_deduction"),
               actions=("contributing", "withdrawing", "transferring")),
    ),
    make_source(
        "cra_resp",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/registered-education-savings-plans-resps.html",
        "cra", "RESP, CESG, CLB grants",
        Facets("resp", actions=("contributing", "opening_account")),
    ),
    make_source(
        "cra_investment_income",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/about-your-tax-return/tax-return/completing-a-tax-return/personal-income/investment-income.html",
        "cra", "Capital gains / dividend taxation basics",
        Facets("non_registered",
               tax_concepts=("capital_gains", "dividend_tax_credit"),
               investment_vehicles=("stocks", "mutual_funds"),
               actions=("filing_taxes",)),
    ),
    make_source(
        "cra_folio_dividends",
        "https://www.canada.ca/en/revenue-agency/services/tax/technical-information/income-tax/income-tax-folios-index/series-3-property-investments-savings-plans/series-3-property-investments-savings-plan-folio-2-dividends/income-tax-folio-s3-f2-c2-taxable-dividends-corporations-resident-canada.html",
        "cra", "Technical dividend taxation folio (dense — good for depth)",
        Facets("non_registered",
               tax_concepts=("dividend_tax_credit",),
               investment_vehicles=("stocks",),
               actions=("filing_taxes",)),
    ),

    # --- Primary: CIRO — national SRO, Cloudflare-blocked for plain HTTP ---
    # Institutional/regulatory content — doesn't map to a specific
    # account_type, hence "none"; retrieval leans on source_authority +
    # topic for this one rather than the facets.
    make_source(
        "ciro_office_investor",
        "https://www.ciro.ca/office-investor",
        "ciro", "Dealer regulation, investor protection, complaints, fraud",
        Facets("none"),
    ),

    # --- Primary: AMF — Quebec provincial regulator, WAF-blocked for plain HTTP ---
    make_source(
        "amf_general_public",
        "https://lautorite.qc.ca/en/general-public",
        "amf", "Quebec-specific securities/insurance regulation",
        Facets("none"),
    ),

    # --- Primary: OSC — Ontario regulator, fetches directly over plain HTTP.
    # jurisdiction left at its registry default ("none"): this is general
    # investing education, not Ontario-specific rules, despite the publisher.
    make_source(
        "osc_gsam_home",
        "https://www.getsmarteraboutmoney.ca/",
        "osc_gsam", "Investing basics hub",
        Facets("none", investment_vehicles=("stocks", "etfs", "mutual_funds", "bonds")),
    ),
    make_source(
        "osc_investing_academy",
        "https://academy.getsmarteraboutmoney.ca/",
        "osc_gsam", "Structured investing lessons",
        Facets("none", investment_vehicles=("stocks", "etfs", "mutual_funds", "bonds")),
    ),

    # --- Secondary: journalism, banks, private entities — no jurisdictional authority ---
    make_source(
        "fpcanada_home",
        "https://www.fpcanada.ca/",
        "fpcanada", "Consumer life-moment financial planning",
        Facets("none"),
    ),
    make_source(
        "moneysense_home",
        "https://www.moneysense.ca/",
        "moneysense", "Canadian personal-finance journalism",
        Facets("none"),
    ),
    make_source(
        "rbc_tfsa",
        "https://www.rbcroyalbank.com/investments/tfsa.html",
        "rbc", "Practical TFSA account-opening steps",
        Facets("tfsa", actions=("opening_account", "contributing")),
    ),
    make_source(
        "td_tfsa",
        "https://www.td.com/ca/en/personal-banking/personal-investing/products/investment-plans/tfsa",
        "td", "Practical TFSA account-opening steps",
        Facets("tfsa", actions=("opening_account", "contributing")),
    ),
    make_source(
        "questrade_learning",
        "https://www.questrade.com/learning",
        "questrade", "Practical DIY-investing steps",
        Facets("none", investment_vehicles=("stocks", "etfs", "options", "crypto")),
    ),
]
