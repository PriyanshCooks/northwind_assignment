"""Reads map_uk.csv, map_in.csv and group_coa.csv. Codes stay text; a code with two targets keeps both rows."""
from pathlib import Path

from app.domain.ledger import CoaAccount, MapRow
from app.domain.quarantine import Quarantined
from app.parsers.contracts import Contract, read_rows

MAP = Contract(("local_code", "local_name", "group_code"))
COA = Contract(
    ("account_code", "account_name", "account_type", "statement", "cash_flow_category", "normal_balance"),
    allowed={
        "account_type": frozenset({"Asset", "Liability", "Equity", "Revenue", "Expense"}),
        "statement": frozenset({"BS", "PL"}),
        "normal_balance": frozenset({"Debit", "Credit"}),
    },
)


def load_coa(path: Path) -> dict[str, CoaAccount]:
    accounts = {}
    for row in read_rows(path, COA):
        v = row.values
        accounts[v["account_code"]] = CoaAccount(
            ref=row.ref, code=v["account_code"], name=v["account_name"], account_type=v["account_type"],
            statement=v["statement"], cash_flow_category=v["cash_flow_category"], normal_balance=v["normal_balance"],
        )
    return accounts


def load_map(path: Path, entity: str) -> dict[str, list[MapRow]]:
    """All rows per local code. More than one row for a code is ambiguous and is never resolved by taking the first."""
    index: dict[str, list[MapRow]] = {}
    for row in read_rows(path, MAP):
        v = row.values
        entry = MapRow(
            ref=row.ref, entity=entity, local_code=v["local_code"],
            local_name=Quarantined(text=v["local_name"]), group_code=v["group_code"],
        )
        index.setdefault(entry.local_code, []).append(entry)
    return index
