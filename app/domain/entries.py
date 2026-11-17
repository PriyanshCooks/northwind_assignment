"""Postings and entries: every consolidated balance is a sum of postings, each with its origin and source rows."""
from decimal import Decimal
from typing import Literal

from app.domain.refs import Model, Money, SourceRef

Origin = Literal["IMPORT", "JOURNAL", "REVALUE", "TRANSLATION", "ELIMINATION", "ACQUISITION"]


class Posting(Model):
    """One piece of a balance. `amount` is debit-positive in `ccy`. `rate_ref` names the rate used, if any."""

    entity: str
    account: str
    amount: Money
    ccy: str
    origin: Origin
    sources: tuple[SourceRef, ...]
    rate_ref: str | None = None
    note: str = ""


class Entry(Model):
    """A set of postings that must balance (debits equal credits): revaluation, in-transit, elimination, acquisition."""

    id: str
    origin: Origin
    description: str
    lines: tuple[Posting, ...]

    def difference(self) -> Decimal:
        return sum((line.amount for line in self.lines), Decimal(0))

    def is_balanced(self) -> bool:
        return self.difference() == 0


class TraceStep(Model):
    """One step of a calculation, kept so an auditor can walk a figure down to file:line."""

    figure: str
    formula: str
    inputs: tuple[str, ...]
    result: Money | None
    sources: tuple[SourceRef, ...] = ()
