"""Reads map_uk.csv, map_in.csv and group_coa.csv, and gives each trial-balance line a mapping verdict."""
from pathlib import Path

from app.domain.ledger import CoaAccount, LedgerLine, MappedLine, MapRow
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


def exact_name_match(row: MapRow, coa: dict[str, CoaAccount]) -> str | None:
    """The mapped account contradicts the local name: the name equals a different group account of another type."""
    name = row.local_name.text.strip().lower()
    mapped_type = coa[row.group_code].account_type
    same_name = [a.code for a in coa.values() if a.name.lower() == name and a.account_type != mapped_type]
    return same_name[0] if len(same_name) == 1 else None


def classify(line: LedgerLine, rows: list[MapRow] | None, coa: dict[str, CoaAccount]) -> MappedLine:
    """Mapping outcomes: OK, SUSPECT (rule-confirmed contradiction), UNMAPPED, AMBIGUOUS. `rows` None means the
    entity reports in group codes (the US), so the code is its own group code."""
    if rows is None:
        known = line.local_code in coa
        return MappedLine(line=line, group_code=line.local_code if known else None, map_ref=None,
                          verdict="OK" if known else "UNMAPPED")
    if not rows:
        return MappedLine(line=line, group_code=None, map_ref=None, verdict="UNMAPPED")
    if len({r.group_code for r in rows}) > 1:
        return MappedLine(line=line, group_code=None, map_ref=rows[0].ref, verdict="AMBIGUOUS")
    row = rows[0]
    if row.group_code not in coa:
        return MappedLine(line=line, group_code=None, map_ref=row.ref, verdict="UNMAPPED")
    proposed = exact_name_match(row, coa)
    return MappedLine(
        line=line, group_code=row.group_code, map_ref=row.ref,
        verdict="SUSPECT" if proposed else "OK", proposed_group_code=proposed,
    )
