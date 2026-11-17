"""The 12 control figures, each Determined, Provisional (with its open items) or Unknown (with its reason)."""
from decimal import Decimal

from app.core.acquisition import AcquisitionFigures
from app.core.intercompany import IcResult
from app.core.reserve import ReserveResult
from app.core.revalue import RevalueResult, restated_amount
from app.core.statements import Balances, net_assets, profit, revenue, total_assets
from app.domain.figures import Determined, Figure, Provisional, Unknown
from app.domain.journals import Disposition
from app.domain.runs import Inputs
from app.parsers.fx_rates import FxTable

KEYS = (
    "group_revenue", "group_profit", "profit_owners", "profit_nci", "nci_closing", "goodwill_closing",
    "translation_reserve_movement", "total_assets", "total_equity", "intercompany_difference", "sgd_bank_gbp",
    "journals",
)


def _wrap(value: Decimal, open_items: tuple[str, ...]) -> Figure:
    return Provisional(value=value, open_items=open_items) if open_items else Determined(value=value)


def sgd_figure(inputs: Inputs, fx: FxTable) -> Figure:
    """The UK SGD bank at the closing rate. Without a GBP/SGD closing rate it is Unknown, never an estimate."""
    lines = [line for line in inputs.trial_balances.get("UK", []) if line.txn_ccy == "SGD"]
    amounts = [restated_amount(line, fx) for line in lines]
    if not lines or any(a is None for a in amounts):
        return Unknown(reason="fx_rates.csv has no GBP/SGD closing rate, so the SGD 40,000 bank balance cannot be "
                              "restated; it is carried at its booked GBP value inside total assets")
    return Determined(value=sum((a for a in amounts if a is not None), Decimal(0)))


def build_figures(
    inputs: Inputs, fx: FxTable, balances: Balances, res: ReserveResult, acq: AcquisitionFigures, ic: IcResult,
    dispositions: list[Disposition], rev: RevalueResult,
) -> dict[str, Figure]:
    coa = inputs.coa
    gaps = tuple(
        f"{ln.entity} {ln.local_code} {ln.txn_ccy} {ln.txn_amount} carried at its booked {ln.amount}: no closing rate"
        for ln in rev.unresolved
    )
    suspense = balances.get("UNMAPPED", Decimal(0))
    unmapped = (f"an UNMAPPED balance of {suspense} is carried in a suspense line",) if suspense != 0 else ()
    counts = {"posted": 0, "rejected": 0, "held": 0}
    for d in dispositions:
        counts[{"POST": "posted", "REJECT": "rejected", "HOLD": "held"}[d.status]] += 1
    group_profit = profit(balances, coa)
    return {
        "group_revenue": _wrap(revenue(balances, coa), unmapped),
        "group_profit": _wrap(group_profit, gaps + unmapped),
        "profit_owners": _wrap(res.owners_profit, gaps + unmapped),
        "profit_nci": _wrap(acq.nci_profit, unmapped),
        "nci_closing": _wrap(res.nci_closing, unmapped),
        "goodwill_closing": Determined(value=acq.goodwill_gbp),
        "translation_reserve_movement": _wrap(res.movement_balance, unmapped),
        "total_assets": _wrap(total_assets(balances, coa), gaps + unmapped),
        "total_equity": _wrap(net_assets(balances, coa), gaps + unmapped),
        "intercompany_difference": (
            Determined(value=ic.difference) if ic.difference is not None
            else Unknown(reason="the intercompany difference needs a USD closing rate and fx_rates.csv has none")
        ),
        "sgd_bank_gbp": sgd_figure(inputs, fx),
        "journals": Determined(value=counts),
    }


def all_unknown(reason: str) -> dict[str, Figure]:
    """A blocked run still answers every key: null with the reason, never a crash and never a guess."""
    return {key: Unknown(reason=reason) for key in KEYS}
