"""Translate entity postings into GBP: closing rate for the balance sheet, average for the period for income."""
from datetime import date
from decimal import Decimal

from app.domain.entries import Posting
from app.domain.runs import Inputs
from app.parsers.fx_rates import FxTable


class ConsolidationBlocked(Exception):
    """A step cannot run because an input it needs is missing. The run continues; dependent figures are Unknown."""


def _rate(fx: FxTable, ccy: str, rate_type: str, entity: str) -> Decimal:
    rate = fx.units_per_gbp(ccy, rate_type)
    if rate is None:
        raise ConsolidationBlocked(f"{entity} cannot be translated: no {ccy} {rate_type} rate in fx_rates.csv")
    return rate


def translate(postings: list[Posting], inputs: Inputs, fx: FxTable, year_end: date) -> list[Posting]:
    """Policy 2. Equity accounts are skipped: group equity comes from the prior-year file and the reserve, not from
    translating each entity's own equity lines."""
    out = []
    for p in postings:
        account = inputs.coa.get(p.account)
        if account is not None and account.account_type == "Equity":
            continue
        entity = inputs.entities[p.entity]
        if account is not None and account.statement == "PL":
            rate_type = fx.average_type(entity.acquisition_date, year_end)
            if rate_type is None:
                raise ConsolidationBlocked(f"{p.entity} has no average rate for the period it was owned")
        else:
            rate_type = "closing"
        rate = _rate(fx, p.ccy, rate_type, p.entity)
        out.append(p.model_copy(update={"amount": p.amount / rate, "ccy": "GBP", "rate_ref": fx.ref(p.ccy, rate_type)}))
    return out
