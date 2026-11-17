"""Checks that must hold for any input: every TB, journal and entry balances; IC nets to zero; the sheet balances."""
from dataclasses import dataclass
from decimal import Decimal

from app.core.reserve import ReserveResult
from app.domain.entries import Entry, Posting
from app.domain.ledger import MappedLine
from app.domain.runs import Inputs

CLOSE = Decimal("0.000001")  # exact arithmetic to 50 digits: anything above this is a real difference, not rounding


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str


def _check(name: str, ok: bool, detail: str = "") -> Check:
    return Check(name=name, ok=ok, detail=detail)


def _by_entity(postings: list[Posting]) -> dict[str, Decimal]:
    totals: dict[str, Decimal] = {}
    for p in postings:
        totals[p.entity] = totals.get(p.entity, Decimal(0)) + p.amount
    return totals


def _by_journal(postings: list[Posting]) -> dict[str, Decimal]:
    totals: dict[str, Decimal] = {}
    for p in postings:
        if p.origin == "JOURNAL":
            key = p.note.split()[0]
            totals[key] = totals.get(key, Decimal(0)) + p.amount
    return totals


def check_invariants(
    inputs: Inputs, mapped: list[MappedLine], local: list[Posting], entries: list[Entry], eliminations: list[Entry],
    balances: dict[str, Decimal], statements: dict[str, dict[str, object]], reserve: ReserveResult, tolerance: Decimal,
) -> list[Check]:
    out = []
    tb_totals = {e: sum((line.amount for line in lines), Decimal(0)) for e, lines in inputs.trial_balances.items()}
    out.append(_check("every trial balance balances", all(v == 0 for v in tb_totals.values()), str(tb_totals)))
    kept = len(mapped) == sum(len(lines) for lines in inputs.trial_balances.values())
    out.append(_check("no trial-balance line is dropped by mapping", kept))
    unbalanced = {k: v for k, v in _by_journal(local).items() if v != 0}
    out.append(_check("every posted journal balances", not unbalanced, str(unbalanced)))
    broken = [e.id for e in entries + eliminations if not e.is_balanced()]
    out.append(_check("every revaluation, in-transit and elimination entry balances", not broken, ", ".join(broken)))
    off = {k: v for k, v in _by_entity(local).items() if abs(v) > CLOSE}
    out.append(_check("every entity balances in its own currency after posting", not off, str(off)))
    ic = {a: balances.get(a, Decimal(0)) for a in ("1250", "2150", "4200", "6300")}
    zero = all(abs(v) <= CLOSE for v in ic.values())
    out.append(_check("intercompany balances and income net to zero", zero, str(ic)))
    sheet = statements["balance_sheet"]
    gap = sheet["total_assets"] - sheet["total_liabilities"] - sheet["total_equity"]  # type: ignore[operator]
    out.append(_check("the translated balance sheet balances including the reserve", abs(gap) <= tolerance, str(gap)))
    out.append(_check("the two reserve routes agree", abs(reserve.difference) <= tolerance, str(reserve.difference)))
    closing = statements["changes_in_equity"]["rows"][-1]["total"]  # type: ignore[index]
    tie = abs(closing - sheet["total_equity"]) <= tolerance
    out.append(_check("changes in equity closes to the balance sheet", tie))
    return out
