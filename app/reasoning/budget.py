"""A per-run limit that counts units sent to a model live (not dollars): replayed answers are free and do not count."""
from dataclasses import dataclass, field

from app.llm.ledger import Ledger


@dataclass
class UnitBudget:
    limit: int | None = None
    start: set[str] = field(default_factory=set)

    def begin(self, ledger: Ledger) -> "UnitBudget":
        self.start = set(ledger.new_keys)
        return self

    def spent(self, ledger: Ledger) -> int:
        return len(ledger.new_keys - self.start)

    def exhausted(self, ledger: Ledger) -> bool:
        return self.limit is not None and self.spent(ledger) >= self.limit
