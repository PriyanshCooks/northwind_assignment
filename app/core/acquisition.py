"""The India acquisition: post-acquisition period, goodwill and non-controlling interest (policy 4)."""
from dataclasses import dataclass
from decimal import Decimal

from app.core.translate import ConsolidationBlocked
from app.domain.entries import Posting
from app.domain.refs import SourceRef
from app.domain.runs import Inputs
from app.parsers.fx_rates import FxTable
from app.parsers.mappings import resolve_account

INDIA = "IN"  # the entity of in_pl_monthly.csv


def india_period_postings(postings: list[Posting], inputs: Inputs) -> list[Posting]:
    """India's trial balance is nine months. Income and expense come from the monthly file for the months owned;
    profit for the months before completion moves to reserves, because it belongs to the seller."""
    entity = inputs.entities[INDIA]
    if entity.acquisition_date is None:
        return postings
    cutoff = f"{entity.acquisition_date.year}-{entity.acquisition_date.month:02d}"
    kept = [p for p in postings if not _is_india_income(p, inputs)]
    owned = [r for r in inputs.india_monthly if r.month >= cutoff]
    before = [r for r in inputs.india_monthly if r.month < cutoff]
    for row in owned:
        account = resolve_account(inputs.maps, inputs.coa, INDIA, row.ledger_code)
        kept.append(Posting(entity=INDIA, account=account or "UNMAPPED", amount=row.amount, ccy=entity.currency,
                            origin="IMPORT", sources=(row.ref,), note=f"{row.ledger_code} {row.month}"))
    if before:
        kept.append(Posting(
            entity=INDIA, account="3200", amount=sum((r.amount for r in before), Decimal(0)), ccy=entity.currency,
            origin="ACQUISITION", sources=tuple(r.ref for r in before),
            note=f"profit before completion ({before[0].month} to {before[-1].month}) carried to reserves",
        ))
    if sum((p.amount for p in kept if p.entity == INDIA), Decimal(0)) != 0:
        raise ConsolidationBlocked("the India monthly file does not tie to its trial balance")
    return kept


def _is_india_income(p: Posting, inputs: Inputs) -> bool:
    account = inputs.coa.get(p.account)
    return p.entity == INDIA and p.origin == "IMPORT" and account is not None and account.statement == "PL"


@dataclass(frozen=True)
class AcquisitionFigures:
    goodwill_inr: Decimal
    goodwill_gbp: Decimal
    nci_at_acquisition: Decimal
    nci_closing: Decimal
    nci_profit: Decimal
    nci_translation: Decimal
    india_net_assets_inr: Decimal
    india_profit_gbp: Decimal
    closing_rate: Decimal
    spot_rate: Decimal
    refs: tuple[SourceRef, ...]


def acquisition_figures(
    inputs: Inputs, fx: FxTable, local: list[Posting], translated: list[Posting],
) -> AcquisitionFigures:
    note = inputs.acquisition
    closing, spot = fx.units_per_gbp("INR", "closing"), fx.units_per_gbp("INR", "spot")
    if closing is None or spot is None:
        raise ConsolidationBlocked("India goodwill needs the INR closing and spot rates")
    owned = note.interest_pct / 100
    goodwill_inr = note.consideration_inr - owned * note.net_assets_at_completion
    net_assets = sum((p.amount for p in local if p.entity == INDIA and _is_balance_sheet(p, inputs)), Decimal(0))
    profit = -sum((p.amount for p in translated if p.entity == INDIA and _is_income(p, inputs)), Decimal(0))
    nci_share = 1 - owned
    at_acquisition = nci_share * note.net_assets_at_completion / spot
    closing_nci = nci_share * net_assets / closing
    nci_profit = nci_share * profit
    return AcquisitionFigures(
        goodwill_inr=goodwill_inr, goodwill_gbp=goodwill_inr / closing, nci_at_acquisition=at_acquisition,
        nci_closing=closing_nci, nci_profit=nci_profit, nci_translation=closing_nci - at_acquisition - nci_profit,
        india_net_assets_inr=net_assets, india_profit_gbp=profit, closing_rate=closing,
        spot_rate=spot,
        refs=tuple(note.refs.values()),
    )


def _is_balance_sheet(p: Posting, inputs: Inputs) -> bool:
    account = inputs.coa.get(p.account)
    return account is not None and account.statement == "BS" and account.account_type != "Equity"


def _is_income(p: Posting, inputs: Inputs) -> bool:
    account = inputs.coa.get(p.account)
    return account is not None and account.statement == "PL"
