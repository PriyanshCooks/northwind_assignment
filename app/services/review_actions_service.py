"""A reviewer's decision on one finding. Pass acknowledges it and moves no figure; a pass on a journal the rules held
also closes that held item, which the existing flow already treats as 'reviewed, stays out of the figures'. Override is
refused unless the rule table allows it, and the only override the engine has is the mapping one (D02)."""
from typing import Any

from app.services import decisions_service as decisions
from app.services import pipeline_service as pipeline
from app.services.inputs_service import NoSuchFile, file_path, held_target, load_scan, mapping_target
from app.services.registry_service import Registry
from app.services.rows_service import read_rows, row_for_line
from app.services.rule_text import actions_for


def decide(registry: Registry, run_id: str, name: str, key: str, action: str, reviewer: str,
           note: str) -> dict[str, Any]:
    rows = read_rows(file_path(registry, run_id, name))
    scan = load_scan(registry, run_id)
    item = next((i for i in scan.findings if i["key"] == key and i["file"] == name), None)
    if item is None:
        raise NoSuchFile(f"{key} is not a finding of {name}")
    if not reviewer.strip():
        raise ValueError("enter your name before you decide")
    mapping = mapping_target(item, scan.open_items)
    if action == "override" and not actions_for(item["code"], mapping is not None)["override"]:
        raise ValueError(actions_for(item["code"], False)["override_note"] or "this finding cannot be overridden")
    target = mapping if action == "override" else held_target(item, scan.open_items)
    if target:
        pipeline.decide(registry, run_id, reviewer.strip(), {target: "approve"})
    at = row_for_line(rows, item["line"])
    cells = [] if at is None else rows[at]["cells"]
    entry = decisions.record(registry.folder(run_id), key, action, reviewer, note,
                             decisions.evidence_hash(key, item["claim"], cells))
    return {"decision": entry, "run": registry.meta(run_id)}
