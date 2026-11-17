"""issues.json: every problem found, with file, line, amount affected and what the system did."""
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

from app.domain.figures import Provisional, Unknown
from app.utils.hashing import dumps
from app.utils.money import round_tree
from app.writers.statements import write_text

if TYPE_CHECKING:
    from app.services.run_service import Consolidation


def _row(
    code: str, severity: str, claim: str, file: str, line: int | None, amount: Decimal | None, action: str,
) -> dict[str, object]:
    return {"code": code, "severity": severity, "file": file, "line": line, "amount_affected": amount,
            "action": action, "claim": claim}


def issue_rows(run: "Consolidation") -> list[dict[str, object]]:
    rows = []
    for f in run.findings:
        row = _row(f.code, f.severity, f.claim, f.file, f.line, f.amount_affected, f.action)
        if f.subject:
            row["journal"] = f.subject
        if f.quoted_text is not None:
            row["quoted_text"] = f.quoted_text.text
        rows.append(row)
    if run.blocked:
        rows.append(_row("RUN", "BLOCK", run.blocked, "", None, None, "blocked"))
    for name, figure in run.figures.items():
        if isinstance(figure, Unknown):
            rows.append(_row("FIG", "FLAG", f"{name} is null: {figure.reason}", "fx_rates.csv", None, None, "blocked"))
        elif isinstance(figure, Provisional):
            rows.append(_row("FIG", "NOTE", f"{name} is provisional: {'; '.join(figure.open_items)}", "tb_uk.csv", 3,
                             None, "assumed"))
    if run.ic is not None and run.ic.difference is not None:
        for cause, value in run.ic.causes.items():
            rows.append(_row("IC", "NOTE", f"intercompany difference cause: {cause}", "intercompany.csv", None, value,
                             "assumed"))
    rows += [_row("CHECK", "BLOCK", f"{c.name}: {c.detail}", "", None, None, "flagged") for c in run.checks if not c.ok]
    return rows


def write_issues(run: "Consolidation", out: Path) -> None:
    write_text(out / "issues.json", dumps(round_tree({"issues": issue_rows(run)})))
