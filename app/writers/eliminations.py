"""eliminations.csv: every revaluation, in-transit and elimination entry, with the rows it comes from."""
import csv
from pathlib import Path
from typing import TYPE_CHECKING

from app.utils.money import fmt2

if TYPE_CHECKING:
    from app.services.run_service import Consolidation

COLUMNS = ("entry_id", "origin", "description", "entity", "account", "account_name", "ccy", "debit", "credit",
           "note", "rate_ref", "source_rows")


def write_eliminations(run: "Consolidation", out: Path) -> None:
    coa = run.ctx.inputs.coa
    entries = list(run.revalue.entries if run.revalue else []) + list(run.ic.entries if run.ic else [])
    with open(out / "eliminations.csv", "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(COLUMNS)
        for entry in entries + run.eliminations:
            for p in entry.lines:
                debit, credit = (fmt2(p.amount), "") if p.amount > 0 else ("", fmt2(-p.amount))
                name = coa[p.account].name if p.account in coa else ""
                writer.writerow([entry.id, entry.origin, entry.description, p.entity, p.account, name, p.ccy, debit,
                                 credit, p.note, p.rate_ref or "", "; ".join(dict.fromkeys(str(s) for s in p.sources))])
