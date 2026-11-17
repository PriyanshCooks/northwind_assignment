"""One deduplicated problem found in the inputs or the run, with the place it came from."""
from typing import Literal

from app.domain.quarantine import Quarantined
from app.domain.refs import Model, Money, SourceRef


class Finding(Model):
    """`key` is stable (code, file, line, field), so the same defect found twice is one finding."""

    key: str
    code: str
    severity: Literal["BLOCK", "FLAG", "NOTE"]
    claim: str
    file: str
    line: int | None
    amount_affected: Money | None
    action: Literal["blocked", "assumed", "flagged", "noted"]
    evidence: tuple[SourceRef, ...] = ()
    quoted_text: Quarantined | None = None

    def merged_with(self, other: "Finding") -> "Finding":
        """Same key found by two detectors: keep the stronger severity and the union of the evidence."""
        order = {"BLOCK": 2, "FLAG": 1, "NOTE": 0}
        winner = self if order[self.severity] >= order[other.severity] else other
        evidence = tuple(dict.fromkeys(self.evidence + other.evidence))
        return winner.model_copy(update={"evidence": evidence})
