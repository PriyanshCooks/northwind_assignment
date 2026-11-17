"""One deduplicated problem found in the inputs or the run, with the place it came from."""
from decimal import Decimal
from typing import Literal

from app.domain.quarantine import Quarantined
from app.domain.refs import Model, Money, SourceRef


def new_finding(
    code: str, severity: Literal["BLOCK", "FLAG", "NOTE"], claim: str, file: str, line: int | None,
    action: Literal["blocked", "assumed", "flagged", "noted"], amount: Decimal | None = None, field: str = "",
    evidence: tuple[SourceRef, ...] = (), quoted: Quarantined | None = None, subject: str | None = None,
) -> "Finding":
    """Build a finding with its stable key (code, file, line, field). `subject` names the journal it is about."""
    key = f"{code}:{file}:{line if line is not None else 0}:{field}"
    return Finding(
        key=key, code=code, severity=severity, claim=claim, file=file, line=line,
        amount_affected=amount, action=action, evidence=evidence, quoted_text=quoted, subject=subject,
    )


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
    subject: str | None = None

    def merged_with(self, other: "Finding") -> "Finding":
        """Same key found by two detectors: keep the stronger severity and the union of the evidence."""
        order = {"BLOCK": 2, "FLAG": 1, "NOTE": 0}
        winner = self if order[self.severity] >= order[other.severity] else other
        evidence = tuple(dict.fromkeys(self.evidence + other.evidence))
        return winner.model_copy(update={"evidence": evidence})
