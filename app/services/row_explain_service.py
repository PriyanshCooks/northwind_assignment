"""One input row explained: the rule in plain words, the evidence, the decision and what the recorded AI review said.
Findings and cards come from the same scan as the row lists in inputs_service; the AI view is replayed, never called."""
from typing import Any

from app.services import decisions_service as decisions
from app.services.cards_service import ai_view
from app.services.inputs_service import NoSuchFile, Scan, file_path, finding_state, load_scan, mapping_target
from app.services.registry_service import Registry
from app.services.rows_service import read_rows, row_for_line
from app.services.rule_text import actions_for, rule_of
from app.utils.hashing import sha256_text

# The AI reviewers read journals and trial-balance mappings only, so only these checks can carry an AI view. The card
# wording matches a finding to a unit by account code, which would give a rate check the mapping review of its account.
AI_CODES = {"D02", "D03", "D04", "D05", "D06", "D07", "D12"}
NO_AI = {"state": "not_reviewed", "text": "Not reviewed by the AI: it reads only journals and trial-balance mappings."}
MAP_FILE = {"UK": "map_uk.csv", "IN": "map_in.csv"}


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
    decided = decisions.latest(registry.folder(run_id))
    mine = [i for i in scan.findings if i["file"] == name and row_for_line(rows, i["line"]) == at]
    unit = _unit_for_row(scan, name, row)
    return {"file": name, "line": line, "cells": row["cells"], "row_hash": sha256_text(repr(row["cells"])),
            "scanned": scan.ready, "findings": [_explained(i, scan, row, unit, decided) for i in mine],
            "ai": _ai_block(unit)}


def _explained(item: dict[str, Any], scan: Scan, row: dict[str, Any], unit: dict[str, Any] | None,
               decided: dict[str, dict[str, Any]]) -> dict[str, Any]:
    card = scan.cards[item["key"]]
    decision = decided.get(item["key"])
    ai = card["ai"] if item["code"] in AI_CODES else NO_AI
    looked = ai["state"] != "not_reviewed"
    return {"key": item["key"], "code": item["code"], "severity": item["severity"], "headline": card["headline"],
            "rule": rule_of(item["code"]), "source": "Rule + AI view" if looked else "Rule",
            "evidence": {"cited": item["refs"] or [f"{item['file']}:{item['line']}"], "values": row["cells"]},
            "rules_decided": card["rules"], "action": item["action"], "ai": ai,
            "state": finding_state(item, row["cells"], decided),
            "decision": {k: decision[k] for k in ("action", "reviewer", "note", "at")} if decision else None,
            "actions": actions_for(item["code"], mapping_target(item, scan.open_items) is not None),
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
