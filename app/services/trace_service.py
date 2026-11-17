"""Walk a figure or an account down to file:line, from the latest recorded run."""
from pathlib import Path

from app.db.connection import connect
from app.db.lineage_service import get_trace, origin_rows
from app.db.runs_service import latest_run_id
from app.utils.money import fmt2


def trace(db_path: Path, target: str) -> list[str]:
    """`target` is a control figure key (goodwill_closing) or a group account code (4100)."""
    conn = connect(db_path)
    run_id = latest_run_id(conn)
    if run_id is None:
        return ["no recorded run: run `python run.py consolidate` first"]
    steps = get_trace(conn, run_id, target)
    if steps is not None:
        return [_step_line(s.formula, s.result, [str(r) for r in s.sources]) for s in steps]
    rows = origin_rows(conn, run_id, target)
    if rows:
        return [_step_line(f"{r.origin} {r.entity} {r.note} ({r.rate_ref or 'no rate'})", r.amount,
                           [str(s) for s in r.sources]) for r in rows]
    return [f"nothing recorded for {target!r}: use a figure key or a group account code"]


def _step_line(text: str, amount: object, sources: list[str]) -> str:
    shown = f" = {fmt2(amount)}" if hasattr(amount, "quantize") else ""  # type: ignore[arg-type]
    where = f"  <- {', '.join(dict.fromkeys(sources))}" if sources else ""
    return f"{text}{shown}{where}"
