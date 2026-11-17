"""D08 required rate present: for every foreign-currency monetary line and every translation the run needs."""
from app.domain.findings import Finding, new_finding
from app.domain.runs import Context
from app.parsers.fx_rates import FxTable


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
