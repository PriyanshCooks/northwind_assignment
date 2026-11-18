"""D08 required rate present: for every foreign-currency monetary line and every translation the run needs.
D15 rate plausibility: a rate that is possible but far from its neighbours or from what the books imply."""
from decimal import Decimal
from statistics import median

from app.domain.findings import Finding, new_finding
from app.domain.runs import Context
from app.parsers.fx_rates import FxTable
from app.utils.money import to_decimal

CHECKED_TYPES = {"closing", "average", "h2_average"}


def d08_required_rates(ctx: Context) -> list[Finding]:
    fx = FxTable(ctx.inputs.rates)
    found = []
    for tb_entity, lines in ctx.inputs.trial_balances.items():
        for line in lines:
            if line.txn_ccy and fx.units_per_gbp(line.txn_ccy, "closing") is None:
                claim = (f"{tb_entity} {line.local_code} holds {line.txn_ccy} {line.txn_amount} but fx_rates.csv "
                         f"has no GBP/{line.txn_ccy} closing rate; it stays at its booked {line.amount} and is "
                         "provisional")
                found.append(new_finding("D08", "FLAG", claim, line.ref.file, line.ref.line, "flagged",
                                         abs(line.amount), "closing_rate", (line.ref,)))
    year_end = ctx.policy.period.end
    for entity in ctx.inputs.entities.values():
        if entity.currency == "GBP":
            continue
        average = fx.average_type(entity.acquisition_date, year_end)
        needed = {"closing": fx.units_per_gbp(entity.currency, "closing"),
                  "average": None if average is None else fx.units_per_gbp(entity.currency, average)}
        if entity.acquisition_date and entity.acquisition_date.year == year_end.year:
            needed["spot"] = fx.units_per_gbp(entity.currency, "spot")
        for name, rate in needed.items():
            if rate is None:
                claim = f"{entity.id} cannot be translated: no {entity.currency} {name} rate in fx_rates.csv"
                found.append(new_finding("D08", "BLOCK", claim, "fx_rates.csv", None, "blocked", None,
                                         f"{entity.id}_{name}"))
    return found


def percent_apart(value: Decimal, reference: Decimal) -> Decimal:
    return abs(value / reference - 1) * 100


def d15_rate_plausibility(ctx: Context) -> list[Finding]:
    """Two rule-only checks, amber and never blocking: a rate far from the same pair's other rates, and a closing
    rate far from the rate a booked foreign amount implies. Tolerances: ASSUMED A14 and A15 in assumptions.toml."""
    near = to_decimal(ctx.assumptions["rate_neighbour_tolerance_pct"])
    implied_tolerance = to_decimal(ctx.assumptions["rate_implied_tolerance_pct"])
    rows = ctx.inputs.rates
    found = []
    for row in rows:
        others = [r.value for r in rows if (r.base, r.quote) == (row.base, row.quote) and r is not row]
        if row.rate_type not in CHECKED_TYPES or not others:
            continue
        reference = median(others)
        apart = percent_apart(row.value, reference)
        if apart > near:
            claim = (f"{row.base}/{row.quote} {row.rate_type} rate {row.value:f} ({row.ref}) is {apart:.1f}% from "
                     f"{reference:f}, the median of the {len(others)} other {row.base}/{row.quote} rates; the "
                     f"tolerance is {near}%. Used as given; check the file for a typo or an inverted pair")
            found.append(new_finding("D15", "FLAG", claim, row.ref.file, row.ref.line, "flagged", None,
                                     f"{row.rate_type}_neighbours", (row.ref,)))
    fx = FxTable(rows)
    for entries in ctx.inputs.trial_balances.values():
        for line in entries:
            closing = fx.units_per_gbp(line.txn_ccy, "closing") if line.txn_ccy else None
            if not (line.txn_ccy and line.txn_amount and line.amount and closing):
                continue
            implied = abs(to_decimal(line.txn_amount) / line.amount)
            apart = percent_apart(closing, implied)
            if apart > implied_tolerance:
                claim = (f"{line.local_code} booked {line.txn_ccy} {line.txn_amount} as GBP {abs(line.amount):f}, "
                         f"which implies {implied:.4f} {line.txn_ccy} per GBP; the closing rate {closing:f} is "
                         f"{apart:.1f}% away (tolerance {implied_tolerance}%). Used as given")
                found.append(new_finding("D15", "FLAG", claim, line.ref.file, line.ref.line, "flagged", None,
                                         "closing_vs_booked", (line.ref,)))
    return found
