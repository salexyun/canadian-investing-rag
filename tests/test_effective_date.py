"""Regression cases for ingestion/chunk.py's extract_effective_date.

Every case is (an excerpt of) a real chunk from the corpus. The "None"
cases are CRA worked examples whose scenario years used to be surfaced
as a chunk's "as of" date in the UI and prompt -- a reviewer caught
"as of 2009" on a chunk about the current TFSA limit.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ingestion"))

from chunk import extract_effective_date  # noqa: E402

RULE_STATEMENTS = [
    # cra_tfsa_calculate_room::0
    ("The TFSA dollar limit for 2026 is $7,000. The dollar limit is added to your "
     "contribution room on January 1, 2026 .", "2026-01-01"),
    # cra_rrsp_deduction_limit::2
    ("18% of your earned income in the previous year the annual RRSP limit "
     "(for 2025, the annual limit is $32,490)", "2025-01-01"),
    # cra_tfsa_calculate_room::2 -- a real rule stated inside an example
    ("based on the annual TFSA dollar limit for 2023 ($6,500) and 2024 ($7,000). "
     "The new annual limit for 2026 is $7,000 and is included in Moira's CRA account", "2026-01-01"),
    # wealthsimple_tfsa::5
    ("Since the earliest accumulation year was 2009, the lifetime limit as of 2026 "
     "is $109,000.", "2026-01-01"),
    ("The new rules apply effective January 1, 2026 to all contribution limits.", "2026-01-01"),
]

WORKED_EXAMPLES = [
    # cra_tfsa_types_investments::1
    "Joe is a resident of Canada. When he turned 18 years of age in 2024, he opened a "
    "TFSA. The dollar limit was $7,000 in 2024 and Joe contributed the full amount.",
    # cra_tfsa_types_investments::2
    "He believed he was entitled to the total annual TFSA dollar limit since the "
    "program began in 2009. David did not know that the dollar limit only applies",
    # cra_tfsa_withdraw::0
    "Any over-contribution you make to your TFSA, even in error, is taxable. From "
    "2014 to the present, the contribution limit",
    # cra_tfsa_contributing_how::3
    "On February 10, 2026, she withdraws $4,000. Her contribution room stays at $3,000 .",
    # cra_tfsa_contributing_how::5
    "Isla's contribution room for 2024 is $7,000 (the 2024 dollar limit).",
    # cra_prpp_contributions::2
    "Benoît knows his RRSP deduction limit for 2025 is $10,000, so he agrees to "
    "contribute $5,000",
    # cra_tfsa_death_successor::20
    "As Miriam only has contribution room of $7,000 for 2026, she now has an excess "
    "TFSA amount of $2,000.",
]


@pytest.mark.parametrize("text,expected", RULE_STATEMENTS)
def test_rule_statement_gets_its_date(text, expected):
    assert extract_effective_date(text) == expected


@pytest.mark.parametrize("text", WORKED_EXAMPLES)
def test_worked_example_gets_no_date(text):
    assert extract_effective_date(text) is None
