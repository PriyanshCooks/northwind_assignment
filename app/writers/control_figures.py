"""control_figures_pb.json (a number, or null) and control_figures_status.json (why null, what is provisional)."""
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

from app.core.figures import KEYS
from app.domain.figures import Determined, Provisional, Unknown
from app.utils.hashing import dumps
from app.utils.money import round_tree
from app.writers.statements import write_text

if TYPE_CHECKING:
    from app.services.run_service import Consolidation

# the brief's appendix: control_figures_<your initials>.json
INITIALS = "pb"


def figure_values(run: "Consolidation") -> dict[str, object]:
    out: dict[str, object] = {}
    for key in KEYS:
        figure = run.figures[key]
        out[key] = None if isinstance(figure, Unknown) else figure.value
    return out


def figure_status(run: "Consolidation") -> dict[str, object]:
    status: dict[str, object] = {}
    for key in KEYS:
        figure = run.figures[key]
        if isinstance(figure, Unknown):
            status[key] = {"status": "unknown", "reason": figure.reason}
        elif isinstance(figure, Provisional):
            status[key] = {"status": "provisional", "open_items": list(figure.open_items)}
        elif isinstance(figure, Determined):
            status[key] = {"status": "determined"}
    causes: dict[str, Decimal] = dict(run.ic.causes) if run.ic else {}
    return {"figures": status, "intercompany_causes": causes, "checks_passed": run.checks_passed,
            "blocked": run.blocked}


def write_control_figures(run: "Consolidation", out: Path) -> None:
    write_text(out / f"control_figures_{INITIALS}.json", dumps(round_tree(figure_values(run))))
    write_text(out / "control_figures_status.json", dumps(round_tree(figure_status(run))))
