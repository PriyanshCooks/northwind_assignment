"""Parsed supplied inputs, and the record of one run."""
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from app.domain.journals import Journal
from app.domain.ledger import CoaAccount, LedgerLine, MapRow, MonthlyRow
from app.domain.policy import Policy
from app.domain.refs import Model, Money, SourceRef


class Entity(Model):
    ref: SourceRef
    id: str
    currency: str
    ownership_pct: Money | None
    acquisition_date: date | None
    tb_file: str


class IcInvoice(Model):
    ref: SourceRef
    reporting_entity: str
    counterparty: str
    doc_ref: str
    doc_date: date
    doc_currency: str
    doc_amount: Money
    booked_currency: str
    booked_amount: Money


class SubledgerControl(Model):
    ref: SourceRef
    entity: str
    ledger: str
    currency: str
    control_total: Money


class PriorEquity(Model):
    ref: SourceRef
    account: str
    amount_gbp: Money


class Acquisition(Model):
    """The acquisition note: what was paid and what was acquired, with the line each figure came from."""

    completion_date: date
    interest_pct: Money
    consideration_inr: Money
    equity_share_capital: Money
    reserves_at_start: Money
    profit_before_completion: Money
    net_assets_at_completion: Money
    refs: dict[str, SourceRef]


class RateRow(Model):
    """One row of fx_rates.csv: `value` is units of `quote` per 1 unit of `base`, direction parsed from the file."""

    ref: SourceRef
    base: str
    quote: str
    rate_type: str
    value: Money
    as_of: str


@dataclass
class Inputs:
    data_dir: Path
    entities: dict[str, Entity]
    trial_balances: dict[str, list[LedgerLine]]
    maps: dict[str, dict[str, list[MapRow]]]
    coa: dict[str, CoaAccount]
    rates: tuple[RateRow, ...]
    journals: list[Journal]
    intercompany: list[IcInvoice]
    subledger: list[SubledgerControl]
    prior_equity: dict[str, PriorEquity]
    acquisition: Acquisition
    india_monthly: list[MonthlyRow]


@dataclass
class Context:
    """Everything a detector or a consolidation step may read: the inputs, the policy and the assumption switches."""

    inputs: Inputs
    policy: Policy
    assumptions: dict[str, bool | str]
