"""A per-run limit that counts units sent to a model live (not dollars): replayed answers are free and do not count."""
from dataclasses import dataclass

from app.llm.ledger import Ledger


@dataclass
class UnitBudget:
    limit: int | None = None
    start: set[str] | None = None

    def begin(self, ledger: Ledger) -> "UnitBudget":
        if self.start is None:  # one budget can span the three checkpoints of a run
            self.start = set(ledger.new_keys)
        return self

    def spent(self, ledger: Ledger) -> int:
        return len(ledger.new_keys - (self.start or set()))

    def exhausted(self, ledger: Ledger) -> bool:
        return self.limit is not None and self.spent(ledger) >= self.limit
