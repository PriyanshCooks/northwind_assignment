"""D13 expectation checks on India's monthly P&L: a step change in the tax rate and identical consecutive months."""
from decimal import Decimal

from app.domain.findings import Finding, new_finding
from app.domain.ledger import MonthlyRow
from app.domain.runs import Context

TAX_GROUP = "8100"
STEP = Decimal("0.05")  # a move of five percentage points between consecutive months is worth a note


def _by_month(ctx: Context) -> dict[str, list[MonthlyRow]]:
    months: dict[str, list[MonthlyRow]] = {}
    for row in ctx.inputs.india_monthly:
        months.setdefault(row.month, []).append(row)
    return dict(sorted(months.items()))


def _tax_rate(ctx: Context, rows: list[MonthlyRow]) -> Decimal | None:
    index = ctx.inputs.maps["IN"]
    def is_tax(row: MonthlyRow) -> bool:
        mapped = index.get(row.ledger_code)
        return mapped is not None and mapped[0].group_code == TAX_GROUP

    tax = sum((r.amount for r in rows if is_tax(r)), Decimal(0))
    pretax = -sum((r.amount for r in rows if not is_tax(r)), Decimal(0))
    return tax / pretax if pretax else None


def _tax_step(ctx: Context, months: dict[str, list[MonthlyRow]]) -> list[Finding]:
    found, previous = [], None
    for month, rows in months.items():
        rate = _tax_rate(ctx, rows)
        if previous and rate is not None and abs(rate - previous[1]) > STEP:
            ref = rows[0].ref
            claim = (f"India effective tax rate moves from {previous[1] * 100:.2f}% in {previous[0]} to "
                     f"{rate * 100:.2f}% in {month}; the data does not explain it")
            found.append(new_finding("D13", "NOTE", claim, ref.file, ref.line, "noted", None, "tax_step", (ref,)))
        previous = (month, rate) if rate is not None else previous
    return found


def _identical_runs(months: dict[str, list[MonthlyRow]]) -> list[Finding]:
    vectors = {m: {r.ledger_code: r.amount for r in rows} for m, rows in months.items()}
    names = list(vectors)
    found: list[list[str]] = []
    run: list[str] = []
    for i, month in enumerate(names):
        if i and vectors[month] == vectors[names[i - 1]]:
            run = run or [names[i - 1]]
            run.append(month)
        elif len(run) >= 3:
            found.append(run)
            run = []
        else:
            run = []
    if len(run) >= 3:
        found.append(run)
    out = []
    for months_in_run in found:
        ref = months[months_in_run[0]][0].ref
        claim = f"India months {', '.join(months_in_run)} are identical on every account"
        out.append(new_finding("D13", "NOTE", claim, ref.file, ref.line, "noted", None, "identical_months", (ref,)))
    return out


def d13_expectations(ctx: Context) -> list[Finding]:
    months = _by_month(ctx)
    return _tax_step(ctx, months) + _identical_runs(months)
