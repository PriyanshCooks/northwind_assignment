"""Deterministic scoring of reviewer results against labels. No judge model: every number is a set comparison."""
from dataclasses import dataclass

from app.services.review_service import UnitResult
from tests.evals.labels import expected


@dataclass(frozen=True)
class Score:
    units: int
    true_positive: int  # claims that are right and survived grounding
    false_negative: int  # real defects that were not reported
    false_positive: int  # verified claims that are not defects
    raw_claims: int  # claims before grounding
    dropped: int  # claims grounding removed
    unverified: int
    exact_units: int  # units whose verified set equals the label

    @property
    def recall(self) -> float:
        total = self.true_positive + self.false_negative
        return self.true_positive / total if total else 1.0

    @property
    def false_alarm_rate(self) -> float:
        reported = self.true_positive + self.false_positive
        return self.false_positive / reported if reported else 0.0

    @property
    def ungrounded_rate(self) -> float:
        return self.dropped / self.raw_claims if self.raw_claims else 0.0


def score(pairs: list[tuple[UnitResult, set[str]]]) -> Score:
    tp = fn = fp = raw = dropped = unverified = exact = 0
    for result, truth in pairs:
        said = set(result.grounded.verified)
        tp, fn, fp = tp + len(said & truth), fn + len(truth - said), fp + len(said - truth)
        raw += len(said) + len(result.grounded.dropped) + len(result.grounded.unverified)
        dropped += len(result.grounded.dropped)
        unverified += len(result.grounded.unverified)
        exact += said == truth
    return Score(len(pairs), tp, fn, fp, raw, dropped, unverified, exact)


def supplied(results: list[UnitResult]) -> list[tuple[UnitResult, set[str]]]:
    return [(r, expected(r.unit.unit_id, r.unit.kind)) for r in results]


def lines(name: str, s: Score) -> list[str]:
    return [f"{name}: {s.units} units, recall {s.recall:.2f}, false alarms {s.false_alarm_rate:.2f}, "
            f"ungrounded {s.ungrounded_rate:.2f}, unverified {s.unverified}, exact {s.exact_units}/{s.units}"]
