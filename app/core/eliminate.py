"""Eliminate intercompany balances and income, and the investments in subsidiaries (policy 5)."""
from decimal import Decimal

from app.core.acquisition import AcquisitionFigures
from app.core.translate import ConsolidationBlocked
from app.domain.entries import Entry, Posting
from app.domain.refs import SourceRef
from app.domain.runs import Inputs

# group chart accounts for intercompany items and for the investments the US parent holds
IC_RECEIVABLE, IC_PAYABLE, IC_INCOME, IC_EXPENSE = "1250", "2150", "4200", "6300"
INVESTMENT = {"UK": "1600", "IN": "1610"}


def total(postings: list[Posting], account: str, entity: str | None = None) -> Decimal:
    mine = (p.amount for p in postings if p.account == account and (entity is None or p.entity == entity))
    return sum(mine, Decimal(0))


def _sources(postings: list[Posting], *accounts: str) -> tuple[SourceRef, ...]:
    refs = [s for p in postings if p.account in accounts for s in p.sources]
    return tuple(dict.fromkeys(refs))


def _leg(account: str, amount: Decimal, note: str, sources: tuple[SourceRef, ...], rate: str | None = None) -> Posting:
    return Posting(entity="GROUP", account=account, amount=amount, ccy="GBP", origin="ELIMINATION",
                   sources=sources, rate_ref=rate, note=note)


def ic_balances(translated: list[Posting]) -> Entry:
    """Policy 5: eliminated in full. Both sides were restated to the closing rate, so they should be equal."""
    receivable, payable = total(translated, IC_RECEIVABLE), total(translated, IC_PAYABLE)
    src = _sources(translated, IC_RECEIVABLE, IC_PAYABLE)
    return Entry(
        id="ELIM-IC-BALANCES", origin="ELIMINATION", description="Eliminate intercompany receivable and payable",
        lines=(_leg(IC_PAYABLE, -payable, "intercompany payable", src),
               _leg(IC_RECEIVABLE, -receivable, "intercompany receivable", src)),
    )


def ic_income_expense(translated: list[Posting], residual_account: str) -> Entry:
    """Income at the average rate against expense as booked or recorded: the difference goes to 7300 (policy 5)."""
    income, expense = total(translated, IC_INCOME), total(translated, IC_EXPENSE)
    src = _sources(translated, IC_INCOME, IC_EXPENSE)
    return Entry(
        id="ELIM-IC-INCOME", origin="ELIMINATION", description="Eliminate intercompany management fees",
        lines=(_leg(IC_INCOME, -income, "management fee income", src),
               _leg(IC_EXPENSE, -expense, "management fee expense", src),
               _leg(residual_account, income + expense, "rate difference on elimination", src)),
    )


def _uk_investment(local: list[Posting], translated: list[Posting]) -> Entry:
    investment = total(translated, INVESTMENT["UK"], "US")
    capital = -total(local, "3100", "UK")
    src = _sources(translated, INVESTMENT["UK"]) + _sources(local, "3100")
    return Entry(
        id="ELIM-INV-UK", origin="ELIMINATION", description="Eliminate the investment in Northwind UK",
        lines=(_leg(INVESTMENT["UK"], -investment, "investment at closing", src),
               _leg("3100", capital, "UK share capital eliminated", src),
               _leg("3300", investment - capital, "translation difference on the investment", src)),
    )


def _india_investment(inputs: Inputs, translated: list[Posting], acq: AcquisitionFigures) -> Entry:
    note = inputs.acquisition
    investment = total(translated, INVESTMENT["IN"], "US")
    owners_share = note.interest_pct / 100 * note.net_assets_at_completion / acq.spot_rate
    src = _sources(translated, INVESTMENT["IN"]) + acq.refs
    return Entry(
        id="ELIM-INV-IN", origin="ACQUISITION",
        description="Eliminate the investment in Northwind India and recognise goodwill",
        lines=(_leg(INVESTMENT["IN"], -investment, "investment at closing", src),
               _leg("1700", acq.goodwill_gbp, "goodwill held in INR, retranslated at closing", src),
               _leg("3200", owners_share, "owners' share of net assets at completion, at the acquisition-date rate (policy 2)", src),
               _leg("3300", investment - acq.goodwill_gbp - owners_share, "translation difference", src)),
    )


def investments(
    inputs: Inputs, local: list[Posting], translated: list[Posting], acq: AcquisitionFigures,
) -> list[Entry]:
    """Remove each investment against what it bought. The equity legs (3100, 3200, 3300) are shown for the auditor;
    group equity itself is built in reserve.py, so only the 1600, 1610 and 1700 legs reach the consolidated balances."""
    entries = [_uk_investment(local, translated), _india_investment(inputs, translated, acq)]
    if any(not e.is_balanced() for e in entries):
        raise ConsolidationBlocked("an investment elimination does not balance")
    return entries
