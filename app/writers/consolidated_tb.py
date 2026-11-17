"""consolidated_tb.csv: the consolidated trial balance in GBP, each balance with its source rows."""
import csv
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

from app.core.lineage import origin_rows
from app.domain.refs import SourceRef
from app.utils.money import fmt2

if TYPE_CHECKING:
    from app.services.run_service import Consolidation

COLUMNS = ("group_code", "group_name", "debit_gbp", "credit_gbp", "source_rows")


def _sources(refs: list[SourceRef]) -> str:
    return "; ".join(dict.fromkeys(str(r) for r in refs))


def tb_rows(run: "Consolidation") -> list[tuple[str, str, Decimal, list[SourceRef]]]:
    """(account, name, debit-positive amount, sources). Equity is opening group equity from the prior-year file, the
    closing reserve, and NCI before its share of this year's profit, which sits in the open income accounts."""
    inputs, coa = run.ctx.inputs, run.ctx.inputs.coa
    sources: dict[str, list[SourceRef]] = {}
    for row in origin_rows(run):
        sources.setdefault(row.account, []).extend(row.sources)
    rows = [(a, coa[a].name if a in coa else "Unmapped (suspense)", v, sources.get(a, []))
            for a, v in sorted(run.balances.items()) if v != 0]
    prior, acq = inputs.prior_equity, run.acquisition
    if run.reserve is None or acq is None:
        return rows
    equity = {
        "3100": (-prior["3100"].amount_gbp, [prior["3100"].ref]),
        "3200": (-prior["3200"].amount_gbp, [prior["3200"].ref]),
        "3300": (-run.reserve.closing, [prior["3300"].ref]),
        "3400": (-(prior["3400"].amount_gbp + acq.nci_at_acquisition + acq.nci_translation),
                 [prior["3400"].ref, *acq.refs]),
    }
    return rows + [(a, coa[a].name, amount, refs) for a, (amount, refs) in equity.items()]


def write_consolidated_tb(run: "Consolidation", out: Path) -> None:
    with open(out / "consolidated_tb.csv", "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(COLUMNS)
        for account, name, amount, refs in tb_rows(run):
            debit, credit = (fmt2(amount), "") if amount > 0 else ("", fmt2(-amount))
            writer.writerow([account, name, debit, credit, _sources(refs)])
