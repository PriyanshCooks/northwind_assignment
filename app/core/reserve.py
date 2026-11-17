"""Translation reserve (account 3300), worked out by two routes that must agree (assumption A12: 0.01)."""
from dataclasses import dataclass
from decimal import Decimal

from app.core.acquisition import INDIA, AcquisitionFigures
from app.core.eliminate import INVESTMENT, total
from app.core.statements import Balances, Coa, net_assets, profit
from app.core.translate import ConsolidationBlocked
from app.domain.entries import Posting
from app.domain.runs import Inputs
from app.parsers.fx_rates import FxTable


@dataclass(frozen=True)
class ReserveResult:
    opening: Decimal
    closing: Decimal
    movement_balance: Decimal
    movement_components: Decimal
    components: dict[str, Decimal]
    owners_profit: Decimal
    nci_closing: Decimal
    retained_closing: Decimal

    @property
    def difference(self) -> Decimal:
        return self.movement_balance - self.movement_components


def _equity(local: list[Posting], coa: Coa, entity: str, kinds: tuple[str, ...]) -> Decimal:
    return -sum((p.amount for p in local if p.entity == entity and p.account in coa
                 and coa[p.account].account_type in kinds and coa[p.account].statement == "BS"), Decimal(0))


def _entity_profit(local: list[Posting], coa: Coa, entity: str) -> Decimal:
    income = (p.amount for p in local if p.entity == entity and p.account in coa and coa[p.account].statement == "PL")
    return -sum(income, Decimal(0))


def _rates(fx: FxTable) -> dict[str, Decimal]:
    wanted = {"usd_close": ("USD", "closing"), "usd_open": ("USD", "opening"), "usd_avg": ("USD", "average"),
              "usd_spot": ("USD", "spot"), "inr_close": ("INR", "closing"), "inr_spot": ("INR", "spot"),
              "inr_h2": ("INR", "h2_average")}
    found = {name: fx.units_per_gbp(ccy, rate_type) for name, (ccy, rate_type) in wanted.items()}
    missing = [name for name, value in found.items() if value is None]
    if missing:
        raise ConsolidationBlocked(f"the reserve needs rates that fx_rates.csv does not give: {', '.join(missing)}")
    return {name: value for name, value in found.items() if value is not None}


def components(
    inputs: Inputs, fx: FxTable, local: list[Posting], translated: list[Posting], acq: AcquisitionFigures,
) -> dict[str, Decimal]:
    """Policy 2: exchange differences from the opening net assets (closing against opening rate), from profit (closing
    against average) and from India (closing against the completion-date rate), less the differences on the two
    investments, which the group eliminates."""
    r, coa = _rates(fx), inputs.coa
    note, owned = inputs.acquisition, inputs.acquisition.interest_pct / 100
    us_open = _equity(local, coa, "US", ("Equity",))
    us_profit = _entity_profit(local, coa, "US")
    india_profit_inr = _entity_profit(local, coa, INDIA)
    uk_inv, in_inv = total(local, INVESTMENT["UK"], "US"), total(local, INVESTMENT["IN"], "US")
    close_usd, close_inr = 1 / r["usd_close"], 1 / r["inr_close"]
    return {
        "us_opening_net_assets": us_open * (close_usd - 1 / r["usd_open"]),
        "us_profit": us_profit * (close_usd - 1 / r["usd_avg"]),
        "india_net_assets_and_profit_owners": owned * (
            note.net_assets_at_completion * (close_inr - 1 / r["inr_spot"])
            + india_profit_inr * (close_inr - 1 / r["inr_h2"])),
        "india_goodwill": acq.goodwill_inr * (close_inr - 1 / r["inr_spot"]),
        "uk_investment_retranslation_removed": -uk_inv * (close_usd - 1 / r["usd_open"]),
        "india_investment_retranslation_removed": -in_inv * (close_usd - 1 / r["usd_spot"]),
    }


def reserve(
    inputs: Inputs, fx: FxTable, local: list[Posting], translated: list[Posting], balances: Balances,
    acq: AcquisitionFigures,
) -> ReserveResult:
    """Balance route: equity is fixed by net assets, so the reserve is what is left after capital, retained earnings
    (opening plus owners' profit, assumption A11) and NCI. Components route: the sum of the exchange differences."""
    prior = inputs.prior_equity
    group_profit = profit(balances, inputs.coa)
    owners = group_profit - acq.nci_profit
    nci = prior["3400"].amount_gbp + acq.nci_closing
    retained = prior["3200"].amount_gbp + owners
    closing = net_assets(balances, inputs.coa) - prior["3100"].amount_gbp - retained - nci
    parts = components(inputs, fx, local, translated, acq)
    return ReserveResult(
        opening=prior["3300"].amount_gbp, closing=closing, movement_balance=closing - prior["3300"].amount_gbp,
        movement_components=sum(parts.values(), Decimal(0)), components=parts, owners_profit=owners,
        nci_closing=nci, retained_closing=retained,
    )
