"""Generate the output at any time. With every item answered it is the normal build. With items unanswered it is a
Draft: the same engine run, the same files, nothing applied that nobody decided (the engine only applies what is signed
off). Unanswered items stay listed as problems; nothing here closes one."""
from pathlib import Path
from typing import Any

from app.orchestrator.nodes import consolidate, export, intake
from app.orchestrator.state import RunState
from app.services import inputs_service as inputs
from app.services.pipeline_service import NotReady, build, run_log
from app.services.registry_service import Registry
from app.services.run_output_service import input_hash
from app.services.run_service import build_context, stage


def unanswered(registry: Registry, run_id: str) -> dict[str, Any]:
    """Everything still a problem: items the engine waits on and findings nobody has passed or overridden."""
    scan = inputs.load_scan(registry, run_id)
    findings = []
    for name in sorted({f["file"] for f in scan.findings}):
        view = inputs.rows_view(registry, run_id, name, scan)
        rows = [f for r in view["rows"] for f in r["findings"]] + view["file_findings"]
        findings += [{"key": f["key"], "file": name, "line": f["line"], "code": f["code"], "severity": f["severity"],
                      "headline": f["headline"], "state": f["state"]} for f in rows if f["state"] in {"open", "stale"}]
    # a held journal or a waiting mapping override is the same problem as its open finding, so it is counted once
    open_keys = {f["key"] for f in findings}
    covered = {t for i in scan.findings if i["key"] in open_keys
               for t in (inputs.held_target(i, scan.open_items), inputs.mapping_target(i, scan.open_items)) if t}
    alone = [t for t in scan.open_items if t not in covered]
    return {"engine_items": scan.open_items, "findings": findings, "problems": len(findings) + len(alone),
            "draft": bool(scan.open_items or findings)}


def generate(registry: Registry, run_id: str) -> dict[str, Any]:
    meta = registry.meta(run_id)
    if meta["status"] == "new":
        raise NotReady("scan the files first: nothing has been analysed yet")
    if meta["status"] == "awaiting_review":
        state = registry.state(run_id)
        state = RunState(**{**state, **intake(state)})
        for node in (consolidate, export):
            state = RunState(**{**state, **node(state)})
        stamp = input_hash(registry.data_dir(run_id), registry.config_dir(run_id))
        registry.update(run_id, built=True, generated_for=stamp)
        report = _report(registry, run_id, state)
    else:
        report = build(registry, run_id)
    left = unanswered(registry, run_id)
    return report | {"draft": left["draft"], "unanswered": left}


def _report(registry: Registry, run_id: str, state: RunState) -> dict[str, Any]:
    run = stage(build_context(Path(state["data_dir"]), Path(state["config_dir"])))
    gates = [{"name": c.name, "ok": c.ok, "detail": c.detail} for c in run.checks]
    return {"gates": gates, "passed": run.checks_passed, "blocked": run.blocked, "stages": run_log(registry, run_id)}
