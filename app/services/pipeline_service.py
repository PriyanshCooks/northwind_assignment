"""The steps behind the UI, each a thin call into an existing service: analyse and resume go through the same graph
the command line uses, review advice is replayed from the ledger only, and the gates are the engine's own checks."""
from pathlib import Path
from typing import Any

from app.config import load_overrides
from app.llm.factory import load_llm_config
from app.llm.ledger import Ledger
from app.orchestrator.graph import resume_graph, run_graph, thread_for
from app.orchestrator.state import RunState
from app.services.overrides_service import override_states, review_queue
from app.services.registry_service import Registry
from app.services.review_service import review_all
from app.services.run_service import build_context, stage
from app.services.upload_service import file_status


class NotReady(Exception):
    """The step cannot run yet. The message says what is missing."""


def _checkpoints(registry: Registry, run_id: str) -> Path:
    return registry.folder(run_id) / "checkpoints.db"


def _store(registry: Registry, run_id: str, state: RunState) -> dict[str, Any]:
    return registry.update(run_id, status=state["status"], open_items=state.get("open_items", []),
                           blocked=state.get("blocked"), checks_passed=state.get("checks_passed"))


def analyse(registry: Registry, run_id: str) -> dict[str, Any]:
    bad = [r["name"] for r in file_status(registry.data_dir(run_id)) if not r["present"] or r["error"]]
    if bad:
        raise NotReady("fix or upload these files first: " + ", ".join(str(n) for n in bad))
    thread = thread_for(registry.data_dir(run_id), registry.config_dir(run_id))
    registry.update(run_id, thread=thread)
    return _store(registry, run_id, run_graph(registry.state(run_id), _checkpoints(registry, run_id)))


def decide(registry: Registry, run_id: str, approver: str, decisions: dict[str, str]) -> dict[str, Any]:
    meta = registry.meta(run_id)
    if meta["status"] != "awaiting_review":
        raise NotReady("this run is not waiting for a decision")
    unknown = sorted(set(decisions) - set(meta["open_items"]))
    if unknown:
        raise NotReady("not open for decision: " + ", ".join(unknown))
    answer = {"approver": approver, "decisions": decisions}
    return _store(registry, run_id, resume_graph(meta["thread"], answer, _checkpoints(registry, run_id)))


def _advice(registry: Registry, run_id: str) -> list[dict[str, Any]]:
    """Recorded model advice. 'replay' never calls a model: a unit with no recorded answer reads 'not recorded'."""
    ctx = build_context(registry.data_dir(run_id), registry.config_dir(run_id))
    cfg = load_llm_config()
    rows = []
    for r in review_all(ctx, cfg, Ledger(cfg.ledger_path), "replay"):
        if r.grounded.verified or r.grounded.unverified or r.grounded.dropped or r.missed:
            rows.append({"kind": r.unit.kind, "unit": r.unit.unit_id, "source": r.source,
                         "recorded": r.source == "model", "verified": list(r.grounded.verified),
                         "unverified": list(r.grounded.unverified), "missed": list(r.missed),
                         "dropped": [{"claim": c, "why": w} for c, w in r.grounded.dropped]})
    return rows


def review_view(registry: Registry, run_id: str) -> dict[str, Any]:
    ctx = build_context(registry.data_dir(run_id), registry.config_dir(run_id))
    run = stage(ctx)
    states = override_states(load_overrides(registry.config_dir(run_id) / "overrides.toml"), ctx.inputs)
    keep = ("key", "code", "severity", "claim", "file", "line", "action")
    return {
        "findings": [{k: v for k, v in f.model_dump(mode="json").items() if k in keep} for f in run.findings],
        "dispositions": [d.model_dump(mode="json") for d in run.dispositions],
        "queue": review_queue(run.findings, states),
        "open_items": registry.meta(run_id)["open_items"],
        "advice": _advice(registry, run_id),
    }


def build(registry: Registry, run_id: str) -> dict[str, Any]:
    """The gates are the engine's own invariant and oracle checks, run again on this run's files."""
    if registry.meta(run_id)["status"] != "done":
        raise NotReady("decide the open items first: the run has not finished")
    run = stage(build_context(registry.data_dir(run_id), registry.config_dir(run_id)))
    registry.update(run_id, built=True)
    gates = [{"name": c.name, "ok": c.ok, "detail": c.detail} for c in run.checks]
    return {"gates": gates, "passed": run.checks_passed, "blocked": run.blocked}
