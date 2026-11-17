"""One function per stage, shared by the LangGraph graph and the plain runner. Each returns a partial state update.

A node rebuilds what it needs from the files named in the state (the whole run takes about 20 ms), so nothing large
has to be checkpointed and a resumed process starts from the same bytes."""
from pathlib import Path
from typing import Any

from app.config import load_overrides
from app.detectors.registry import run_all
from app.orchestrator.state import RunState
from app.services.overrides_service import approve, override_states, reject
from app.services.run_service import build_context, input_hash, record, stage, write_outputs
from app.utils.hashing import sha256_file
from app.utils.logging import RunLogger

Answer = dict[str, Any]


def _log(state: RunState, stage_name: str, event: str, **fields: object) -> None:
    """Every stage of one execution appends to the file that intake started."""
    existing = Path(state["log_file"]) if "log_file" in state else None
    log = RunLogger(Path(state["log_dir"]), state["run_id"], existing)
    log.event(stage_name, event, **fields)
    log.close()


def intake(state: RunState) -> RunState:
    run_id = input_hash(Path(state["data_dir"]), Path(state["config_dir"]))[:16]
    log = RunLogger(Path(state["log_dir"]), run_id)
    log.event("intake", "inputs read", data_dir=state["data_dir"])
    log.close()
    return RunState(run_id=run_id, status="intake", log_file=str(log.path))


def analyse(state: RunState) -> RunState:
    """Run the detectors and list the overrides a person still has to sign off or re-decide."""
    ctx = build_context(Path(state["data_dir"]), Path(state["config_dir"]))
    findings = run_all(ctx)
    states = override_states(load_overrides(Path(state["config_dir"]) / "overrides.toml"), ctx.inputs)
    waiting = [s.override.target for s in states if s.state in {"open", "stale"}]
    for f in findings:
        _log(state, "analyse", "finding", finding_key=f.key, code=f.code, severity=f.severity, action=f.action)
    _log(state, "analyse", "findings", count=len(findings), waiting=waiting)
    return RunState(status="analysed", open_items=waiting)


def apply_answer(state: RunState, answer: Answer) -> RunState:
    """A person's answer: {'approver': name, 'decisions': {target: 'approve' | 'reject'}}. The rest stay open."""
    config_dir = Path(state["config_dir"])
    inputs = build_context(Path(state["data_dir"]), config_dir).inputs
    decided: list[str] = []
    for target in state.get("open_items", []):
        choice = answer.get("decisions", {}).get(target)
        if choice == "approve":
            approve(config_dir / "overrides.toml", inputs, target, answer["approver"])
        elif choice == "reject":
            reject(config_dir / "overrides.toml", target, answer["approver"])
        else:
            continue
        decided.append(target)
    remaining = [t for t in state.get("open_items", []) if t not in decided]
    _log(state, "resolve", "answered", decided=decided, approver=answer.get("approver"))
    return RunState(status="resolved", open_items=remaining, decided=decided)


def consolidate(state: RunState) -> RunState:
    run = stage(build_context(Path(state["data_dir"]), Path(state["config_dir"])))
    for d in run.dispositions:
        _log(state, "consolidate", "journal disposition", journal=d.journal_id, status=d.status)
    for c in run.checks:
        _log(state, "verify", "gate", check=c.name, passed=c.ok)
    _log(state, "consolidate", "done", blocked=run.blocked, checks_passed=run.checks_passed)
    return RunState(status="consolidated", blocked=run.blocked, checks_passed=run.checks_passed)


def export(state: RunState) -> RunState:
    config_dir, out_dir = Path(state["config_dir"]), Path(state["out_dir"])
    run = stage(build_context(Path(state["data_dir"]), config_dir))
    write_outputs(run, out_dir, config_dir)
    record(run, Path(state["db_path"]), Path(state["config_dir"]))
    hashes = {p.name: sha256_file(p) for p in sorted(out_dir.iterdir()) if p.is_file()}
    _log(state, "export", "outputs written", folder=str(out_dir))
    _log(state, "run", "finished", blocked=run.blocked, checks_passed=run.checks_passed)
    return RunState(status="done", output_hashes=hashes)
