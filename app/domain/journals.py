"""Manual journals as supplied, and the decision taken on each."""
from datetime import date
from decimal import Decimal
from typing import Literal

from app.domain.quarantine import Quarantined
from app.domain.refs import Model, Money, SourceRef


class JournalLine(Model):
    ref: SourceRef
    account: str
    debit: Money
    credit: Money
    memo: Quarantined | None = None
    memo_ref: SourceRef | None = None


class Journal(Model):
    ref: SourceRef
    id: str
    entity: str
    date: date
    description: Quarantined
    prepared_by: str
    lines: tuple[JournalLine, ...]

    def total_debit(self) -> Decimal:
        return sum((line.debit for line in self.lines), Decimal(0))

    def total_credit(self) -> Decimal:
        return sum((line.credit for line in self.lines), Decimal(0))


class Disposition(Model):
    """POST, REJECT (invalid for FY2024) or HOLD (needs a human). Set by rule or override, never by a model."""

    journal_id: str
    status: Literal["POST", "REJECT", "HOLD"]
    reasons: tuple[str, ...]
    decided_by: Literal["RULE", "OVERRIDE"] = "RULE"
