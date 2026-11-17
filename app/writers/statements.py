"""balance_sheet.json, profit_and_loss.json and changes_in_equity.json, rounded to 2 decimals only here."""
from pathlib import Path
from typing import TYPE_CHECKING

from app.domain.figures import Provisional
from app.utils.hashing import dumps
from app.utils.money import round_tree

if TYPE_CHECKING:
    from app.services.run_service import Consolidation


def write_text(path: Path, text: str) -> None:
    path.write_text(text + "\n", encoding="utf-8", newline="\n")


def write_statements(run: "Consolidation", out: Path) -> None:
    for name in ("balance_sheet", "profit_and_loss", "changes_in_equity"):
        body = dict(run.statements[name])
        assets = run.figures.get("total_assets")
        if name == "balance_sheet" and isinstance(assets, Provisional):
            body["provisional"] = list(assets.open_items)
        write_text(out / f"{name}.json", dumps(round_tree(body)))
