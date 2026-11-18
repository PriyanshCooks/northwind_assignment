"""Claims the code can check and finds false. These are dropped as "contradicted" and never shown as a suspicion:
a suspicion means the code cannot tell, not that the code has looked and the claim failed."""
from decimal import Decimal

from app.reasoning.evidence import Evidence
from app.reasoning.text_checks import DATE, WORD, invalid_date

RATE_FLAGS = frozenset({"unit_or_direction_suspect", "inconsistent_with_neighbours", "value_not_plausible"})
NATURE_FLAGS = frozenset({"nature_mismatch", "label_contradicts_meaning"})
NONNEGATIVE = frozenset({"fig:total_assets", "fig:group_revenue", "fig:goodwill_closing", "fig:nci_closing"})


def contradicted_line(flag: str, cite: str, line: str, quoted: list[str], evidence: Evidence) -> str | None:
    """Why a line claim is false, or None when the code cannot say."""
    quotes_a_date = any(DATE.search(q) for q in quoted)
    if flag == "value_not_plausible" and quotes_a_date and not invalid_date(line, evidence.last_year):
        return "contradicted: every date on the line is a valid date inside the period"
    gap = evidence.rate_gaps.get(cite)
    if flag in RATE_FLAGS and gap is not None and gap <= evidence.rate_tolerance:
        return (f"contradicted: the rate is {gap:.1f}% from its pair's other rates, inside the "
                f"{evidence.rate_tolerance}% tolerance")
    if flag in NATURE_FLAGS and cite in evidence.nature_agrees:
        return "contradicted: the account name and the group account it maps to have the same nature"
    if flag == "no_valid_name" and WORD.search(line) is not None:
        return "contradicted: the line has a name"
    return None


def contradicted_calc(concern: str, calc_id: str, evidence: Evidence) -> str | None:
    """Why a calculation concern is false, or None when the code cannot say."""
    result: Decimal | None = evidence.results.get(calc_id)
    if concern == "sign_implausible" and calc_id in NONNEGATIVE and result is not None and result >= 0:
        return "contradicted: the result is not negative"
    return None
