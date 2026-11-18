"""The calculation behind one output row, read from the run's evidence store: a control figure gives its formula steps,
a group account gives the postings that make it. Nothing is recomputed here."""
from typing import Any

from app.db.connection import connect
from app.db.lineage_service import get_trace, origin_rows
from app.db.runs_service import latest_run_id
from app.services.registry_service import Registry
from app.utils.money import fmt2


def _amount(value: object) -> str | None:
    return fmt2(value) if hasattr(value, "quantize") else None  # type: ignore[arg-type]


def _where(sources: Any) -> list[str]:
    return list(dict.fromkeys(str(s) for s in sources))


def calculation(registry: Registry, run_id: str, target: str) -> dict[str, Any] | None:
    """`target` is a control figure key or a group account code. None when nothing was recorded for it."""
    conn = connect(registry.folder(run_id) / "run.db")
    recorded = latest_run_id(conn)
    if recorded is None:
        return None
    steps = get_trace(conn, recorded, target)
    if steps is not None:
        return {"target": target, "kind": "figure", "steps": [
            {"formula": s.formula, "result": _amount(s.result), "sources": _where(s.sources)} for s in steps]}
    rows = origin_rows(conn, recorded, target)
    if not rows:
        return None
    return {"target": target, "kind": "account", "steps": [
        {"formula": f"{r.origin} {r.entity} {r.note} (rate: {r.rate_ref or 'none'})", "result": _amount(r.amount),
         "sources": _where(r.sources)} for r in rows]}
