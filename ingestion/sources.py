"""List of pages to ingest.

See data/README.md for the full vetting (legitimacy, appropriateness,
fetchability) behind each entry, and ingestion/schema.py for what
source_authority, jurisdiction, and the facets mean and their allowed
values.

Every entry is validated against ingestion/schema.py's controlled
vocabularies at import time — an unregistered authority, an invalid
jurisdiction, or a typo'd facet value fails immediately instead of
silently corrupting trust-tiering downstream.

Coverage against the closed ACCOUNT_TYPES set is complete as of the
LIRA/LRSP fix (see that section below) — every account type now has at
least one source. Extend deliberately as real gaps turn up, not by
convention drift; each addition below documents the specific gap it
closes.
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
    # jurisdiction left at its registry default ("universal"): this is general
    # investing education, not Ontario-specific rules, despite the publisher.
    #
    # academy.getsmarteraboutmoney.ca (the whole subdomain, not just specific
    # pages) is unreliable: its course pages returned Cloudflare challenges via
    # headless browser and thin content-free shells via plain HTTP (dropped,
    # see the Pillar 2 section below), and even its homepage started 403'ing
    # on a later fetch run after initially succeeding — confirmed broken at
    # the subdomain level, not a one-off. Dropped entirely; www.getsmarter-
    # aboutmoney.ca (a different subdomain) fetches fine and is kept.
    make_source(
        "osc_gsam_home",
        "https://www.getsmarteraboutmoney.ca/",
        "osc_gsam", "Investing basics hub",
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
    # Added on the source-list sanity check: RBC + TD alone left 4 of the
    # "Big Six" banks (~85% of Canadian banking assets combined)
    # unrepresented, and missed Wealthsimple entirely -- the platform most
    # aligned with this project's own newcomer-focused audience.
    make_source(
        "wealthsimple_tfsa",
        "https://www.wealthsimple.com/en-ca/learn/what-is-tfsa",
        "wealthsimple", "Practical TFSA explainer",
        Facets("tfsa", actions=("opening_account", "contributing")),
    ),
    make_source(
        "qtrade_tfsa",
        "https://www.qtrade.ca/en/investor/education/tfsa-trading.html",
        "qtrade", "Practical TFSA explainer",
        Facets("tfsa", actions=("opening_account", "contributing")),
    ),

    # =========================================================================
    # Breadth expansion — five-pillar scope (accounts & vehicles, instruments,
    # taxation, regulation & protection, residency). Each entry below closes a
    # specific, named gap rather than padding for volume — see data/README.md's
    # "Scope" section for the five pillars and the coverage-gap findings that
    # drove this list. URLs for the CRA subpages were pulled directly from the
    # link structure of the already-fetched overview pages, not guessed.
    # =========================================================================

    # --- Pillar 1: TFSA subpages (overview alone was the only TFSA coverage before) ---
    make_source(
        "cra_tfsa_what",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/tax-free-savings-account/what.html",
        "cra", "What a TFSA is, conceptually",
        Facets("tfsa"),
    ),
    make_source(
        "cra_tfsa_opening",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/tax-free-savings-account/opening.html",
        "cra", "Opening a TFSA",
        Facets("tfsa", actions=("opening_account",)),
    ),
    make_source(
        "cra_tfsa_contributing",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/tax-free-savings-account/contributing.html",
        "cra", "Contributing to a TFSA",
        Facets("tfsa", tax_concepts=("contribution_room",), actions=("contributing",)),
    ),
    make_source(
        "cra_tfsa_calculate_room",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/tax-free-savings-account/contributing/calculate-room.html",
        "cra", "Calculating TFSA contribution room",
        Facets("tfsa", tax_concepts=("contribution_room",), actions=("calculating_room",)),
    ),
    make_source(
        "cra_tfsa_overcontribute",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/tax-free-savings-account/contributing/overcontribute.html",
        "cra", "Over-contributing to a TFSA",
        Facets("tfsa", tax_concepts=("over_contribution_penalty",), actions=("contributing",)),
    ),
    make_source(
        "cra_tfsa_withdraw",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/tax-free-savings-account/withdraw.html",
        "cra", "Withdrawing from a TFSA",
        Facets("tfsa", actions=("withdrawing",)),
    ),
    make_source(
        "cra_tfsa_transfer",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/tax-free-savings-account/transfer.html",
        "cra", "Requesting a TFSA transfer (also covers divorce/separation transfers)",
        Facets("tfsa", actions=("transferring",), special_situations=("divorce_separation",)),
    ),
    make_source(
        "cra_tfsa_owing_tax",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/tax-free-savings-account/owing-tax.html",
        "cra", "Owing tax on a TFSA",
        Facets("tfsa", tax_concepts=("over_contribution_penalty",)),
    ),
    make_source(
        "cra_tfsa_owing_tax_pay",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/tax-free-savings-account/owing-tax/pay.html",
        "cra", "How to pay tax owed on a TFSA",
        Facets("tfsa", tax_concepts=("over_contribution_penalty",), actions=("filing_taxes",)),
    ),
    make_source(
        "cra_tfsa_death",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/tax-free-savings-account/death-of-holder.html",
        "cra", "If a TFSA holder dies",
        Facets("tfsa", special_situations=("death_and_estates",)),
    ),
    make_source(
        "cra_tfsa_non_resident",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/tax-free-savings-account/non-resident.html",
        "cra", "If you become a non-resident, and how it affects a TFSA",
        Facets("tfsa", special_situations=("non_resident",)),
    ),
    make_source(
        "cra_tfsa_types_investments",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/tax-free-savings-account/types-investments.html",
        "cra", "What you can hold in a TFSA, including foreign withholding tax on foreign dividends",
        Facets("tfsa", tax_concepts=("withholding_tax",)),
    ),

    # --- Pillar 1: FHSA subpages (overview alone was the only FHSA coverage before) ---
    make_source(
        "cra_fhsa_opening",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/first-home-savings-account/opening-your-fhsas.html",
        "cra", "Opening an FHSA",
        Facets("fhsa", actions=("opening_account",)),
    ),
    make_source(
        "cra_fhsa_contributing",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/first-home-savings-account/contributing-your-fhsa.html",
        "cra", "Participating/contributing to an FHSA",
        Facets("fhsa", tax_concepts=("contribution_room",), actions=("contributing",)),
    ),
    make_source(
        "cra_fhsa_transfers_in",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/first-home-savings-account/transfers-into-your-fhsas.html",
        "cra", "Transfers into an FHSA",
        Facets("fhsa", actions=("transferring",)),
    ),
    make_source(
        "cra_fhsa_withdrawals_transfers_out",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/first-home-savings-account/withdrawals-transfers-out-your-fhsas.html",
        "cra", "Withdrawals and transfers out of an FHSA",
        Facets("fhsa", actions=("withdrawing", "transferring")),
    ),
    make_source(
        "cra_fhsa_tax_deductions",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/first-home-savings-account/tax-deductions-fhsa-contributions.html",
        "cra", "Tax deductions for FHSA contributions",
        Facets("fhsa", tax_concepts=("tax_deduction",)),
    ),
    make_source(
        "cra_fhsa_overcontribute",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/first-home-savings-account/what-happens-contribute-transfer-too-much.html",
        "cra", "What happens if you contribute or transfer too much to an FHSA",
        Facets("fhsa", tax_concepts=("over_contribution_penalty",)),
    ),
    make_source(
        "cra_fhsa_closing",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/first-home-savings-account/closing-your-fhsa.html",
        "cra", "Closing an FHSA",
        Facets("fhsa"),
    ),
    make_source(
        "cra_fhsa_life_events",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/first-home-savings-account/life-events-first-home-savings-accounts.html",
        "cra", "FHSA rules around death, divorce/separation, and becoming a non-resident",
        Facets("fhsa", special_situations=("death_and_estates", "divorce_separation", "non_resident")),
    ),
    make_source(
        "cra_fhsa_investments",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/first-home-savings-account/investments-your-fhsa.html",
        "cra", "What you can hold in an FHSA",
        Facets("fhsa", investment_vehicles=("stocks", "etfs", "mutual_funds", "bonds", "gics")),
    ),

    # --- Pillar 1: RRSP family, including RRIF and PRPP as their own account types ---
    make_source(
        "cra_rrsp_definitions",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/rrsps-related-plans/definitions-rrsps.html",
        "cra", "RRSP glossary/definitions",
        Facets("rrsp"),
    ),
    make_source(
        "cra_rrsp_detail",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/rrsps-related-plans/registered-retirement-savings-plan-rrsp.html",
        "cra", "RRSP explained in detail",
        Facets("rrsp"),
    ),
    make_source(
        "cra_rrsp_turn_71",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/rrsps-related-plans/rrsp-options-when-you-turn-71.html",
        "cra", "RRSP options when you turn 71",
        Facets("rrsp", actions=("withdrawing", "transferring")),
    ),
    make_source(
        "cra_rrsp_hbp",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/rrsps-related-plans/what-home-buyers-plan.html",
        "cra", "The Home Buyers' Plan — withdrawing from an RRSP to buy a home",
        Facets("rrsp", actions=("withdrawing",)),
    ),
    make_source(
        "cra_rrsp_llp",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/rrsps-related-plans/lifelong-learning-plan.html",
        "cra", "The Lifelong Learning Plan — withdrawing from an RRSP for education",
        Facets("rrsp", actions=("withdrawing",)),
    ),
    make_source(
        "cra_rrif",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/registered-retirement-income-fund-rrif.html",
        "cra", "RRIF — closes the account_type coverage gap identified earlier",
        Facets("rrif", actions=("withdrawing",)),
    ),
    make_source(
        "cra_rrsp_important_dates",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/rrsps-related-plans/important-dates-rrsp-rrif-rdsp.html",
        "cra", "Important RRSP/RRIF/RDSP dates",
        Facets("rrsp"),
    ),
    make_source(
        "cra_prpp",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/pooled-registered-pension-plan-prpp-information-individuals.html",
        "cra", "Pooled Registered Pension Plan (PRPP) — closes the account_type coverage gap identified earlier",
        Facets("prpp"),
    ),

    # --- Pillar 1: RESP subpages (overview alone was the only RESP coverage before) ---
    make_source(
        "cra_resp_works",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/registered-education-savings-plans-resps/resp-works.html",
        "cra", "How an RESP works",
        Facets("resp"),
    ),
    make_source(
        "cra_resp_subscriber",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/registered-education-savings-plans-resps/who-a-subscriber.html",
        "cra", "Who can be an RESP subscriber",
        Facets("resp"),
    ),
    make_source(
        "cra_resp_contributions",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/registered-education-savings-plans-resps/resp-contributions.html",
        "cra", "RESP contributions",
        Facets("resp", actions=("contributing",)),
    ),
    make_source(
        "cra_resp_beneficiary",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/registered-education-savings-plans-resps/who-become-a-beneficiary.html",
        "cra", "Designating an RESP beneficiary",
        Facets("resp"),
    ),
    make_source(
        "cra_resp_cesp",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/registered-education-savings-plans-resps/canada-education-savings-programs-cesp.html",
        "cra", "Canada Education Savings Grant (CESG) and Canada Learning Bond (CLB)",
        Facets("resp"),
    ),
    make_source(
        "cra_resp_provincial",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/registered-education-savings-plans-resps/provincial-education-savings-programs.html",
        "cra", "Provincial education savings programs (BC, Quebec)",
        Facets("resp"),
    ),
    make_source(
        "cra_resp_payments",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/registered-education-savings-plans-resps/payments-resp.html",
        "cra", "RESP payments, transfers, and rollovers",
        Facets("resp", actions=("withdrawing", "transferring")),
    ),
    make_source(
        "cra_resp_anti_avoidance",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/registered-education-savings-plans-resps/anti-avoidance-rules-resps.html",
        "cra", "Anti-avoidance rules for RESPs",
        Facets("resp"),
    ),

    # --- Pillar 1: RDSP — closes the account_type coverage gap identified earlier ---
    make_source(
        "cra_rdsp_overview",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/registered-disability-savings-plan-rdsp.html",
        "cra", "What an RDSP is",
        Facets("rdsp"),
    ),
    make_source(
        "cra_rdsp_grant_bond",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/registered-disability-savings-plan-rdsp/canada-disability-savings-grant-canada-disability-savings-bond.html",
        "cra", "Canada Disability Savings Grant and Bond",
        Facets("rdsp", actions=("contributing",)),
    ),

    # --- Pillar 1: LIRA/LRSP — no clean *CRA* consumer page exists (LIRAs/LRSPs
    # are governed by provincial pension legislation, not federal tax rules CRA
    # publishes on), so TD's explainer stayed the only source for a while. Closed
    # properly on the source-list sanity check: FSRA and Retraite Québec are the
    # actual primary regulators for this account type (Ontario/Quebec pension
    # standards legislation), found by checking who regulates *pensions*, not
    # just who was already in the registry — the original "no primary source"
    # framing was really "no primary CRA source", a narrower claim than it read as.
    make_source(
        "td_lira_lrsp",
        "https://www.td.com/ca/en/investing/direct-investing/registered-accounts/lira-lrsp",
        "td", "LIRA/LRSP explained (secondary, practical framing)",
        Facets("lira_lrsp", actions=("transferring", "withdrawing")),
    ),
    make_source(
        "fsra_lira",
        "https://www.fsrao.ca/consumers/pensions/events-may-affect-your-pension/pension-unlocking-non-hardship",
        "fsra", "LIRA/LIF non-hardship unlocking rules under Ontario's Pension Benefits Act",
        Facets("lira_lrsp", actions=("withdrawing",)),
    ),
    make_source(
        "retraitequebec_lirsp",
        "https://www.rrq.gouv.qc.ca/en/programmes/rcr/cri_frv/Pages/CRI_FRV.aspx",
        "retraitequebec", "LIRA/LRSP (LRSP is Quebec's name for it) under the Supplemental Pension Plans Act",
        Facets("lira_lrsp", actions=("transferring",)),
    ),

    # --- Pillar 2: investment vehicles/instruments themselves — previously almost
    # entirely absent; only tax treatment of instruments inside accounts existed.
    #
    # Dropped on the content-quality audit (see data/README.md): gsam_investing_101
    # and gsam_investing_102 (academy.getsmarteraboutmoney.ca is Cloudflare-blocked
    # for headless-browser access, and the plain-HTTP fetch only returns a ~1.8KB
    # shell — the real lesson content is client-rendered and unreachable via either
    # fetch path) and gsam_etf_101 (video-based, ~950 chars of surrounding text,
    # nothing substantive to chunk). Kept gsam_stocks (a real hub with genuine
    # descriptive text, not just links) and added the one linked article that
    # turned out to be real prose rather than another video. ---
    make_source(
        "gsam_stocks",
        "https://www.getsmarteraboutmoney.ca/topics/stocks/",
        "osc_gsam", "Stocks — hub page with real descriptive text, not just links",
        Facets("none", investment_vehicles=("stocks",)),
    ),
    make_source(
        "gsam_stock_market_works",
        "https://www.getsmarteraboutmoney.ca/learning-path/getting-started/how-the-stock-market-works/",
        "osc_gsam", "How the stock market works (real article, ~12K chars — verified before adding)",
        Facets("none", investment_vehicles=("stocks",)),
    ),

    # --- Pillar 3: taxation — foreign reporting/withholding, previously absent ---
    make_source(
        "cra_qualified_investments_folio",
        "https://www.canada.ca/en/revenue-agency/services/tax/technical-information/income-tax/income-tax-folios-index/series-3-property-investments-savings-plans/series-3-property-investments-savings-plan-folio-10-registered-plans-individuals/income-tax-folio-s3-f10-c1-qualified-investments-rrsps-resps-rrifs-rdsps-tfsas.html",
        "cra", "Technical folio: what counts as a qualified investment across all registered plans",
        Facets("none"),
    ),
    make_source(
        "cra_t1135",
        "https://www.canada.ca/en/revenue-agency/services/tax/international-non-residents/information-been-moved/foreign-reporting/foreign-income-verification-statement.html",
        "cra", "T1135 Foreign Income Verification Statement — do you have to report foreign property?",
        Facets("none", tax_concepts=("foreign_reporting",), special_situations=("non_resident",)),
    ),
    make_source(
        "cra_nr4",
        "https://www.canada.ca/en/revenue-agency/services/forms-publications/publications/t4061/nr4-non-resident-tax-withholding-remitting-reporting.html",
        "cra", "NR4 — non-resident tax withholding, remitting, and reporting",
        Facets("none", tax_concepts=("withholding_tax", "foreign_reporting"), special_situations=("non_resident",)),
    ),

    # --- Pillar 4: regulation & investor protection — CIPF/CDIC previously absent entirely ---
    make_source(
        "cipf_about",
        "https://www.cipf.ca/about-us",
        "cipf", "CIPF about-us page — a menu hub, not prose; kept alongside cipf_mandate below (see content-quality audit)",
        Facets("none"),
    ),
    make_source(
        "cipf_mandate",
        "https://www.cipf.ca/about-us/cipf-s-mandate",
        "cipf", "CIPF's actual mandate/purpose — the real content behind the about-us menu",
        Facets("none"),
    ),
    make_source(
        "cdic_home",
        "https://www.cdic.ca/",
        "cdic", "CDIC homepage — mostly a landing page; kept alongside cdic_about below (see content-quality audit)",
        Facets("none", investment_vehicles=("gics",)),
    ),
    make_source(
        "cdic_about",
        "https://www.cdic.ca/about/",
        "cdic", "About CDIC — its vision/purpose as a federal Crown corporation",
        Facets("none", investment_vehicles=("gics",)),
    ),

    # --- Pillar 5: retirement income / residency — CPP/OAS previously absent,
    # despite oas_clawback already sitting in the tax_concepts vocabulary ---
    make_source(
        "canada_public_pensions",
        "https://www.canada.ca/en/services/benefits/publicpensions.html",
        "esdc", "CPP and OAS overview — how public pensions interact with retirement withdrawal planning",
        Facets("none"),
    ),
    make_source(
        "canada_oas",
        "https://www.canada.ca/en/services/benefits/publicpensions/old-age-security.html",
        "esdc", "Old Age Security, including the OAS clawback/repayment threshold",
        Facets("none", tax_concepts=("oas_clawback",)),
    ),

    # =========================================================================
    # Content-quality audit follow-up. A text-length audit of all 66 sources
    # above found ~40% were "thin" (<3000 visible chars despite large HTML) —
    # not a fetch failure, but a systemic CRA pattern: many of the subpages
    # added in the breadth-expansion pass are themselves hub pages (one intro
    # sentence + a link list to deeper leaf pages), not the leaf content itself.
    # These are those leaf pages, pulled from the actual link structure of the
    # hub pages already fetched — same method as the original breadth pass, not
    # guessed. See data/README.md for the full audit writeup.
    # =========================================================================

    # --- TFSA: death-of-holder hub had zero standalone content ---
    make_source(
        "cra_tfsa_death_what_happens",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/tax-free-savings-account/death-of-holder/what-happens.html",
        "cra", "What happens to a TFSA when the holder dies",
        Facets("tfsa", special_situations=("death_and_estates",)),
    ),
    make_source(
        "cra_tfsa_death_successor",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/tax-free-savings-account/death-of-holder/successor-holder.html",
        "cra", "TFSA successor holder rules",
        Facets("tfsa", special_situations=("death_and_estates",)),
    ),
    make_source(
        "cra_tfsa_death_beneficiary",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/tax-free-savings-account/death-of-holder/beneficiary.html",
        "cra", "TFSA designated beneficiary rules",
        Facets("tfsa", special_situations=("death_and_estates",)),
    ),

    # --- TFSA: owing-tax hub had only a boilerplate notice, real content one level deeper ---
    make_source(
        "cra_tfsa_owing_tax_excess",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/tax-free-savings-account/owing-tax/excess.html",
        "cra", "Tax on TFSA excess (over-contribution) amounts",
        Facets("tfsa", tax_concepts=("over_contribution_penalty",)),
    ),
    make_source(
        "cra_tfsa_owing_tax_non_resident",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/tax-free-savings-account/owing-tax/non-resident.html",
        "cra", "Tax on TFSA contributions made while a non-resident",
        Facets("tfsa", tax_concepts=("withholding_tax",), special_situations=("non_resident",)),
    ),
    # Found the same way as the other owing-tax subpages: drilled into the
    # cra_tfsa_owing_tax hub's actual link structure (see data/README.md's
    # Chunking section) rather than assuming the hub's other 3 children were
    # the whole list -- this 4th one was missed the first time through.
    make_source(
        "cra_tfsa_owing_tax_non_permitted_investment",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/tax-free-savings-account/owing-tax/non-permitted-investment.html",
        "cra", "Tax on TFSA holdings that aren't a qualified/permitted investment",
        Facets("tfsa", tax_concepts=("withholding_tax",)),
    ),

    # --- TFSA: contributing hub's remaining real subpages (calculate-room and
    # overcontribute were already fetched directly in the original breadth pass) ---
    make_source(
        "cra_tfsa_contributing_before",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/tax-free-savings-account/contributing/before.html",
        "cra", "What to know before you contribute to a TFSA",
        Facets("tfsa", actions=("contributing",)),
    ),
    make_source(
        "cra_tfsa_contributing_how",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/tax-free-savings-account/contributing/how.html",
        "cra", "How to contribute to a TFSA",
        Facets("tfsa", actions=("contributing",)),
    ),

    # --- FHSA: life-events hub had only one lead-in sentence ---
    make_source(
        "cra_fhsa_marriage_breakdown",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/first-home-savings-account/ending-your-marriage-common-law-partnership.html",
        "cra", "FHSA rules on marriage/common-law breakdown",
        Facets("fhsa", special_situations=("divorce_separation",)),
    ),
    make_source(
        "cra_fhsa_non_residents",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/first-home-savings-account/non-residents-and-fhsas.html",
        "cra", "How non-residency affects an FHSA",
        Facets("fhsa", special_situations=("non_resident",)),
    ),
    make_source(
        "cra_fhsa_death",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/first-home-savings-account/death-and-fhsas.html",
        "cra", "What happens to an FHSA when the holder dies",
        Facets("fhsa", special_situations=("death_and_estates",)),
    ),

    # --- RRSP: cra_rrsp_detail's hub revealed core procedural subpages were
    # missing entirely — the same opening/contributing/transferring/withdrawing
    # coverage TFSA and FHSA already had, RRSP didn't ---
    make_source(
        "cra_rrsp_setting_up",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/rrsps-related-plans/setting-rrsp.html",
        "cra", "Setting up an RRSP",
        Facets("rrsp", actions=("opening_account",)),
    ),
    make_source(
        "cra_rrsp_contributing_prpp",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/rrsps-related-plans/contributing-a-rrsp-prpp.html",
        "cra", "Contributing to an RRSP, PRPP, or SPP — this specific page turned out to be a hub-under-a-hub, one more level than the rest; its two highest-value children below, deliberately stopping there rather than continuing to drill indefinitely",
        Facets("rrsp", actions=("contributing",)),
    ),
    make_source(
        "cra_rrsp_deduction_limit",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/rrsps-related-plans/contributing-a-rrsp-prpp/contributions-affect-your-rrsp-prpp-deduction-limit.html",
        "cra", "How contributions affect your RRSP deduction limit",
        Facets("rrsp", tax_concepts=("contribution_room",), actions=("contributing", "calculating_room")),
    ),
    make_source(
        "cra_rrsp_excess_contributions",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/rrsps-related-plans/contributing-a-rrsp-prpp/what-happens-you-over-your-rrsp-prpp-deduction-limit.html",
        "cra", "What happens if you go over your RRSP/PRPP deduction limit",
        Facets("rrsp", tax_concepts=("over_contribution_penalty",), actions=("contributing",)),
    ),
    make_source(
        "cra_rrsp_transferring",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/rrsps-related-plans/transferring.html",
        "cra", "Transferring RRSP property",
        Facets("rrsp", actions=("transferring",)),
    ),
    make_source(
        "cra_rrsp_making_withdrawals",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/rrsps-related-plans/making-withdrawals.html",
        "cra", "Making withdrawals from an RRSP",
        Facets("rrsp", actions=("withdrawing",)),
    ),
    make_source(
        "cra_rrsp_turn71_options",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/rrsps-related-plans/rrsp-options-when-you-turn-71/options-your-rrsps.html",
        "cra", "RRSP options at age 71 for your own RRSPs",
        Facets("rrsp", actions=("withdrawing", "transferring")),
    ),
    make_source(
        "cra_rrsp_turn71_spousal",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/rrsps-related-plans/rrsp-options-when-you-turn-71/spousal-rrsps-common-law-partner-rrsps.html",
        "cra", "RRSP options at age 71 for spousal/common-law RRSPs",
        Facets("rrsp", actions=("withdrawing", "transferring")),
    ),

    # --- RRIF: same pattern — the overview page pointed to real subpages ---
    make_source(
        "cra_rrif_setting_up",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/registered-retirement-income-fund-rrif/setting-a-rrif.html",
        "cra", "Setting up a RRIF",
        Facets("rrif", actions=("opening_account",)),
    ),
    make_source(
        "cra_rrif_transferring",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/registered-retirement-income-fund-rrif/transferring-your-rrif.html",
        "cra", "Transferring to a RRIF",
        Facets("rrif", actions=("transferring",)),
    ),
    make_source(
        "cra_rrif_receiving_income",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/registered-retirement-income-fund-rrif/receiving-income-a-rrif.html",
        "cra", "Receiving income from a RRIF",
        Facets("rrif", actions=("withdrawing",)),
    ),

    # --- PRPP: kept light — a narrower-audience account type, just the core two ---
    make_source(
        "cra_prpp_joining",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/pooled-registered-pension-plan-prpp-information-individuals/joining-a-prpp.html",
        "cra", "Joining a PRPP",
        Facets("prpp", actions=("opening_account",)),
    ),
    make_source(
        "cra_prpp_contributions",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/pooled-registered-pension-plan-prpp-information-individuals/contributions-a-prpp.html",
        "cra", "Contributing to a PRPP",
        Facets("prpp", actions=("contributing",)),
    ),

    # --- RESP: CESG/CLB hub had only a one-sentence lead-in ---
    make_source(
        "cra_resp_cesg",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/registered-education-savings-plans-resps/canada-education-savings-programs-cesp/canada-education-savings-grant-cesg.html",
        "cra", "Canada Education Savings Grant (CESG) eligibility and amounts",
        Facets("resp"),
    ),
    make_source(
        "cra_resp_clb",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/registered-education-savings-plans-resps/canada-education-savings-programs-cesp/canada-learning-bond.html",
        "cra", "Canada Learning Bond (CLB) eligibility and amounts",
        Facets("resp"),
    ),

    # --- Taxation: investment-income hub had a one-sentence lead-in; the real
    # line-by-line reporting content lives on these three per-line pages ---
    make_source(
        "cra_line_12000_dividends",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/about-your-tax-return/tax-return/completing-a-tax-return/personal-income/line-12000-taxable-amount-dividends-eligible-other-than-eligible-taxable-canadian-corporations.html",
        "cra", "Line 12000/12010 — reporting taxable dividends from Canadian corporations",
        Facets("non_registered", tax_concepts=("dividend_tax_credit",), actions=("filing_taxes",)),
    ),
    make_source(
        "cra_line_12100_interest",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/about-your-tax-return/tax-return/completing-a-tax-return/personal-income/line-12100-interest-other-investment-income.html",
        "cra", "Line 12100 — reporting interest and other investment income",
        Facets("non_registered", actions=("filing_taxes",)),
    ),
    make_source(
        "cra_line_12700_capital_gains",
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/about-your-tax-return/tax-return/completing-a-tax-return/personal-income/line-12700-capital-gains.html",
        "cra", "Line 12700 — reporting taxable capital gains",
        Facets("non_registered", tax_concepts=("capital_gains",), actions=("filing_taxes",)),
    ),
]
