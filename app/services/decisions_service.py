"""The reviewer's decisions on findings: an append-only list in the run folder. A decision is bound to the evidence it
was made on, so it goes stale when the row or the finding changes. Stale and open are worked out when read."""
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.utils.hashing import json_hash

FILE = "decisions.json"
ACTIONS = {"pass": "passed", "override": "overridden"}


def evidence_hash(key: str, claim: str, cells: list[dict[str, str]]) -> str:
    """The finding and the exact row values the reviewer looked at."""
    return json_hash([key, claim, [[c["label"], c["value"]] for c in cells]])


def load(folder: Path) -> list[dict[str, Any]]:
    path = folder / FILE
    return list(json.loads(path.read_text(encoding="utf-8"))) if path.is_file() else []


def record(folder: Path, key: str, action: str, reviewer: str, note: str, evidence: str) -> dict[str, Any]:
    if action not in ACTIONS:
        raise ValueError(f"unknown action: {action}")
    if not reviewer.strip():
        raise ValueError("enter your name before you decide")
    entry = {"target": key, "action": action, "reviewer": reviewer.strip(), "note": note.strip(),
             "evidence_hash": evidence, "at": datetime.now(UTC).isoformat()}
    (folder / FILE).write_text(json.dumps([*load(folder), entry], indent=2), encoding="utf-8")
    return entry


def latest(folder: Path) -> dict[str, dict[str, Any]]:
    """The newest decision for each finding key."""
    return {d["target"]: d for d in load(folder)}


def status(severity: str, decision: dict[str, Any] | None, current: str) -> str:
    """open: needs a decision; noted: nobody has to decide it; passed or overridden; stale: decided on old evidence."""
    if decision is None:
        return "noted" if severity == "NOTE" else "open"
    if decision["evidence_hash"] != current:
        return "stale"
    return ACTIONS[decision["action"]]


def is_open(state: str) -> bool:
    return state in {"open", "stale"}
