"""Source rows as typed values: trial-balance lines, mapping rows, the chart of accounts and monthly P&L rows."""
from typing import Literal

from app.domain.quarantine import Quarantined
from app.domain.refs import Model, Money, SourceRef


class LedgerLine(Model):
    """A standard trial-balance row from any of the three ERP layouts. `amount` is debit-positive, in `currency`."""

    ref: SourceRef
    entity: str
    local_code: str
    local_name: Quarantined
    amount: Money
    currency: str
    cost_centre: str | None = None
    txn_ccy: str | None = None
    txn_amount: Money | None = None


class MapRow(Model):
    ref: SourceRef
    entity: str
    local_code: str
    local_name: Quarantined
    group_code: str


class CoaAccount(Model):
    ref: SourceRef
    code: str
    name: str
    account_type: str
    statement: str
    cash_flow_category: str
    normal_balance: str


class MonthlyRow(Model):
    """One month of one India P&L ledger, debit-positive in INR."""

    ref: SourceRef
    ledger_code: str
    month: str
    amount: Money


class MappedLine(Model):
    line: LedgerLine
    group_code: str | None
    map_ref: SourceRef | None
    verdict: Literal["OK", "REMAPPED", "SUSPECT", "UNMAPPED", "AMBIGUOUS"]
    proposed_group_code: str | None = None
