"""The input workbench's data: each source file as labelled rows with the findings on each row, and for one row the rule
in plain words, the evidence and what the recorded AI review said. Findings come from the same engine run as everything
else; the AI view is replayed from the ledger, so no model is called here."""
import re
from dataclasses import dataclass, field
from typing import Any

from app.parsers.contracts import ContractError
from app.services import ai_service
from app.services import decisions_service as decisions
from app.services.cards_service import build_cards
from app.services.pipeline_service import journal_memos
from app.services.registry_service import Registry
from app.services.rows_service import read_rows, row_for_line
from app.services.run_service import build_context, stage
from app.services.upload_service import EXPECTED_FILES

MAPPING = re.compile(r"^(UK|IN|US) (\S+) is mapped")
JOURNAL = re.compile(r"\bJE-\d+\b")


class NoSuchFile(ValueError):
    """The name is not one of the 15 files, or the run does not hold it."""


@dataclass
class Scan:
    """One engine run over a run's files. `ready` is False when a file breaks its contract, so nothing was scanned."""

    findings: list[dict[str, Any]] = field(default_factory=list)
    cards: dict[str, dict[str, Any]] = field(default_factory=dict)
    units: list[dict[str, Any]] = field(default_factory=list)
    open_items: list[str] = field(default_factory=list)
    ready: bool = False


def load_scan(registry: Registry, run_id: str) -> Scan:
    ctx = build_context(registry.data_dir(run_id), registry.config_dir(run_id))
    try:
        run = stage(ctx)
    except ContractError:
        return Scan()
    items = [{"key": f.key, "code": f.code, "severity": f.severity, "claim": f.claim, "file": f.file, "line": f.line,
              "action": f.action, "subject": f.subject, "refs": [f"{e.file}:{e.line}" for e in f.evidence]}
             for f in run.findings]
    units = ai_service.review_units(registry, run_id)["units"]
    open_items = registry.meta(run_id)["open_items"]
    dispositions = [d.model_dump(mode="json") for d in run.dispositions]
    memos = journal_memos(run)
    cards = {c["key"]: c for c in build_cards(items, units, dispositions, open_items, memos)}
    return Scan(items, cards, units, open_items, True)


def file_path(registry: Registry, run_id: str, name: str) -> Any:
    path = registry.data_dir(run_id) / name
    if name not in EXPECTED_FILES or not path.is_file():
        raise NoSuchFile(f"{name} is not a file of this run")
    return path


def finding_state(item: dict[str, Any], cells: list[dict[str, str]], decided: dict[str, dict[str, Any]]) -> str:
    """open, noted, passed, overridden or stale for one finding, from the reviewer's latest decision on today's row."""
    current = decisions.evidence_hash(item["key"], item["claim"], cells)
    return decisions.status(item["severity"], decided.get(item["key"]), current)


def _finding_row(card: dict[str, Any], item: dict[str, Any], state: str,
                 decision: dict[str, Any] | None) -> dict[str, Any]:
    return {"key": item["key"], "code": item["code"], "severity": item["severity"], "headline": card["headline"],
            "action": item["action"], "line": item["line"], "state": state,
            "decision": {k: decision[k] for k in ("action", "reviewer", "note", "at")} if decision else None}


def _row_review(states: list[str]) -> str:
    """One word for the row: clean (nothing found), open or stale (a decision is needed), reviewed, or noted only."""
    if not states:
        return "clean"
    for state in ("open", "stale"):
        if state in states:
            return state
    return "noted" if set(states) == {"noted"} else "reviewed"


def rows_view(registry: Registry, run_id: str, name: str, scan: Scan | None = None) -> dict[str, Any]:
    """Every row of the file with the findings whose cited line falls on it and the state of each. A finding with no
    row (a header line or no line) is listed under file_findings so none is lost."""
    rows = read_rows(file_path(registry, run_id, name))
    scan = scan or load_scan(registry, run_id)
    decided = decisions.latest(registry.folder(run_id))
    for row in rows:
        row["findings"] = []
    loose: list[dict[str, Any]] = []
    for item in (i for i in scan.findings if i["file"] == name):
        at = row_for_line(rows, item["line"])
        cells = [] if at is None else rows[at]["cells"]
        state = finding_state(item, cells, decided)
        found = _finding_row(scan.cards[item["key"]], item, state, decided.get(item["key"]))
        (loose if at is None else rows[at]["findings"]).append(found)
    for row in rows:
        row["severity"] = _worst([f["severity"] for f in row["findings"]])
        row["review"] = _row_review([f["state"] for f in row["findings"]])
    return {"file": name, "scanned": scan.ready, "total_rows": len(rows), "rows": rows, "file_findings": loose,
            "review": _file_review([f["state"] for r in rows for f in r["findings"]] + [f["state"] for f in loose])}


def _file_review(states: list[str]) -> dict[str, Any]:
    """The file's badge: findings still open (open or stale) out of all findings on it, and one status word."""
    open_count = sum(1 for s in states if decisions.is_open(s))
    status = "clean" if not states else "open" if open_count else "noted" if set(states) == {"noted"} else "reviewed"
    return {"open": open_count, "total": len(states), "status": status}


def file_list(registry: Registry, run_id: str) -> list[dict[str, Any]]:
    """The 15 files with the open/total badge of each. Files the run does not hold are listed as missing."""
    out = []
    scan = load_scan(registry, run_id)
    for name in sorted(EXPECTED_FILES):
        if not (registry.data_dir(run_id) / name).is_file():
            out.append({"name": name, "present": False, "rows": 0, "open": 0, "total": 0, "status": "missing"})
            continue
        view = rows_view(registry, run_id, name, scan)
        out.append({"name": name, "present": True, "rows": view["total_rows"], **view["review"]})
    return out


def _worst(severities: list[str]) -> str | None:
    order = ["BLOCK", "FLAG", "NOTE"]
    return next((s for s in order if s in severities), None)


def mapping_target(item: dict[str, Any], open_items: list[str]) -> str | None:
    """'mapping:UK:2310' when this D02 finding's mapping override still waits for a person, else None."""
    found = MAPPING.match(item["claim"]) if item["code"] == "D02" else None
    target = f"mapping:{found[1]}:{found[2]}" if found else None
    return target if target in open_items else None


def held_target(item: dict[str, Any], open_items: list[str]) -> str | None:
    """'journal:JE-016' when this D06 or D07 finding is about a journal the rules held and nobody has decided."""
    found = JOURNAL.search(item["claim"]) if item["code"] in {"D06", "D07"} else None
    target = f"journal:{found[0]}" if found else None
    return target if target in open_items else None
