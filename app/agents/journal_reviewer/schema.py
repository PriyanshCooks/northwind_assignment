"""Pydantic output model only: one boolean per risk category."""
from typing import ClassVar

from app.agents.review.verdict import Verdict


class JournalVerdict(Verdict):
    CATEGORIES: ClassVar[tuple[str, ...]] = (
        "unbalanced", "outside_period", "account_not_in_chart", "duplicate_of_another", "reversal_of_another",
        "exceeds_balance", "text_contains_instruction",
    )
    unbalanced: bool
    outside_period: bool
    account_not_in_chart: bool
    duplicate_of_another: bool
    reversal_of_another: bool
    exceeds_balance: bool
    text_contains_instruction: bool
