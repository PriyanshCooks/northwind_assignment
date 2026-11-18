"""The input workbench's data: each source file as labelled rows with the findings on each row, and for one row the rule
in plain words, the evidence and what the recorded AI review said. Findings come from the same engine run as everything
else; the AI view is replayed from the ledger, so no model is called here."""
from dataclasses import dataclass, field
from typing import Any

from app.parsers.contracts import ContractError
from app.services import ai_service
from app.services.cards_service import ai_view, build_cards
from app.services.pipeline_service import journal_memos
from app.services.registry_service import Registry
from app.services.rows_service import read_rows, row_for_line
from app.services.rule_text import rule_of
from app.services.run_service import build_context, stage
from app.services.upload_service import EXPECTED_FILES
from app.utils.hashing import sha256_text

# The AI reviewers read journals and trial-balance mappings only, so only these checks can carry an AI view. The card
# wording matches a finding to a unit by account code, which would give a rate check the mapping review of its account.
AI_CODES = {"D02", "D03", "D04", "D05", "D06", "D07", "D12"}
NO_AI = {"state": "not_reviewed", "text": "Not reviewed by the AI: it reads only journals and trial-balance mappings."}
MAP_FILE = {"UK": "map_uk.csv", "IN": "map_in.csv"}


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


def _finding_row(card: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    return {"key": item["key"], "code": item["code"], "severity": item["severity"], "headline": card["headline"],
            "action": item["action"], "line": item["line"]}


def rows_view(registry: Registry, run_id: str, name: str) -> dict[str, Any]:
    """Every row of the file with the findings whose cited line falls on it. A finding with no row (a header line or no
    line) is listed under file_findings so none is lost."""
    rows = read_rows(file_path(registry, run_id, name))
    scan = load_scan(registry, run_id)
    for row in rows:
        row["findings"] = []
    loose: list[dict[str, Any]] = []
    for item in (i for i in scan.findings if i["file"] == name):
        at = row_for_line(rows, item["line"])
        found = _finding_row(scan.cards[item["key"]], item)
        (loose if at is None else rows[at]["findings"]).append(found)
    for row in rows:
        row["severity"] = _worst([f["severity"] for f in row["findings"]])
    return {"file": name, "scanned": scan.ready, "total_rows": len(rows), "rows": rows, "file_findings": loose}


def _worst(severities: list[str]) -> str | None:
    order = ["BLOCK", "FLAG", "NOTE"]
    return next((s for s in order if s in severities), None)


def _unit_for_row(scan: Scan, name: str, row: dict[str, Any]) -> dict[str, Any] | None:
    """The AI reviewed journals (by id) and trial-balance mappings (unit 'ENTITY:code:map line'). Nothing else."""
    cells = {c["label"]: c["value"] for c in row["cells"]}
    if name == "adjustments.json":
        return next((u for u in scan.units if u["unit"] == cells.get("id")), None)
    entity = next((e for e, f in MAP_FILE.items() if f == name), None)
    if entity is None:
        return None
    wanted = f":{row['line']}"
    return next((u for u in scan.units if u["unit"].startswith(f"{entity}:") and u["unit"].endswith(wanted)), None)


def explain_row(registry: Registry, run_id: str, name: str, line: int) -> dict[str, Any]:
    rows = read_rows(file_path(registry, run_id, name))
    at = row_for_line(rows, line)
    if at is None or rows[at]["line"] != line:
        raise NoSuchFile(f"{name} has no row starting at line {line}")
    row = rows[at]
    scan = load_scan(registry, run_id)
    mine = [i for i in scan.findings if i["file"] == name and row_for_line(rows, i["line"]) == at]
    unit = _unit_for_row(scan, name, row)
    return {"file": name, "line": line, "cells": row["cells"], "row_hash": sha256_text(repr(row["cells"])),
            "scanned": scan.ready, "findings": [_explained(i, scan.cards[i["key"]], row, unit) for i in mine],
            "ai": _ai_block(unit)}


def _explained(item: dict[str, Any], card: dict[str, Any], row: dict[str, Any],
               unit: dict[str, Any] | None) -> dict[str, Any]:
    ai = card["ai"] if item["code"] in AI_CODES else NO_AI
    looked = ai["state"] != "not_reviewed"
    return {"key": item["key"], "code": item["code"], "severity": item["severity"], "headline": card["headline"],
            "rule": rule_of(item["code"]), "source": "Rule + AI view" if looked else "Rule",
            "evidence": {"cited": item["refs"] or [f"{item['file']}:{item['line']}"], "values": row["cells"]},
            "rules_decided": card["rules"], "action": item["action"], "ai": ai,
            "dropped": card["dropped"] if looked else [],
            "model_reason": _reason(unit) if looked else None}


def _reason(unit: dict[str, Any] | None) -> str | None:
    """The model's own words from the ledger, only for a unit that has a recorded answer."""
    return unit["answer"].get("reason") if unit and unit["recorded"] and unit["answer"] else None


def _ai_block(unit: dict[str, Any] | None) -> dict[str, Any]:
    """What the AI did on this row whether or not a rule found anything, so 'not flagged' is stated, not implied."""
    view = ai_view(unit)
    reason = _reason(unit)
    return {"looked": unit is not None and unit["recorded"], "unit": unit["unit"] if unit else None,
            "state": view["state"], "text": view["text"], "model_reason": reason,
            "verified": unit["verified"] if unit else [], "dropped": unit["dropped"] if unit else [],
            "missed": unit["missed"] if unit else []}
