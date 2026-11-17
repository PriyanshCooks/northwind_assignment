"""The three trial-balance layouts into one standard row, and India's monthly P&L file."""
from decimal import Decimal
from pathlib import Path

from app.domain.ledger import LedgerLine, MonthlyRow
from app.domain.quarantine import Quarantined
from app.parsers.contracts import Contract, ContractError, RawRow, read_header, read_rows
from app.utils.money import to_decimal

DR_CR = {"dr_cr": frozenset({"Dr", "Cr"})}
DEBIT_CREDIT = Contract(("account_code", "account_name", "debit", "credit"), decimals=("debit", "credit"))
SIGNED_BALANCE = Contract(
    ("nominal_code", "description", "cost_centre", "txn_currency", "txn_amount", "balance"),
    decimals=("txn_amount", "balance"),
)
AMOUNT_DR_CR = Contract(
    ("ledger_code", "ledger_name", "period", "amount", "dr_cr"), decimals=("amount",), allowed=DR_CR,
)
MONTHLY = Contract(("ledger_code", "ledger_name", "month", "amount", "dr_cr"), decimals=("amount",), allowed=DR_CR)


def _number(text: str) -> Decimal:
    return to_decimal(text or "0")


def _signed(row: RawRow) -> Decimal:
    amount = _number(row.values["amount"])
    return amount if row.values["dr_cr"] == "Dr" else -amount


def _line(row: RawRow, entity: str, ccy: str, code: str, name: str, amount: Decimal, **extra: str | None) -> LedgerLine:
    return LedgerLine.model_validate({
        "ref": row.ref, "entity": entity, "local_code": code, "local_name": Quarantined(text=name),
        "amount": amount, "currency": ccy, **extra,
    })


def _debit_credit(row: RawRow, entity: str, ccy: str) -> LedgerLine:
    v = row.values
    return _line(row, entity, ccy, v["account_code"], v["account_name"], _number(v["debit"]) - _number(v["credit"]))


def _signed_balance(row: RawRow, entity: str, ccy: str) -> LedgerLine:
    v = row.values
    foreign = bool(v["txn_currency"]) and v["txn_currency"] != ccy
    return _line(
        row, entity, ccy, v["nominal_code"], v["description"], _number(v["balance"]),
        cost_centre=v["cost_centre"] or None,
        txn_ccy=v["txn_currency"] if foreign else None,
        txn_amount=v["txn_amount"] if foreign and v["txn_amount"] else None,
    )


def _amount_dr_cr(row: RawRow, entity: str, ccy: str) -> LedgerLine:
    v = row.values
    return _line(row, entity, ccy, v["ledger_code"], v["ledger_name"], _signed(row))


ADAPTERS = ((DEBIT_CREDIT, _debit_credit), (SIGNED_BALANCE, _signed_balance), (AMOUNT_DR_CR, _amount_dr_cr))


def load_tb(path: Path, entity: str, ccy: str) -> list[LedgerLine]:
    """Pick the adapter from the header. A header no adapter knows blocks that entity (no guessing)."""
    header = read_header(path)
    for contract, build in ADAPTERS:
        if header == contract.columns:
            return [build(row, entity, ccy) for row in read_rows(path, contract)]
    raise ContractError(path.name, 1, f"unknown trial balance layout {list(header)}")


def load_india_monthly(path: Path) -> list[MonthlyRow]:
    return [
        MonthlyRow(ref=row.ref, ledger_code=row.values["ledger_code"], month=row.values["month"], amount=_signed(row))
        for row in read_rows(path, MONTHLY)
    ]
