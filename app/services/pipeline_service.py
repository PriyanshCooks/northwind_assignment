"""The steps behind the UI, each a thin call into an existing service: analyse and resume go through the same graph
the command line uses, review advice is replayed from the ledger only, and the gates are the engine's own checks."""
import json
import shutil
from pathlib import Path
from typing import Any

from app.config import load_overrides
from app.llm.factory import load_llm_config
from app.llm.ledger import Ledger
from app.orchestrator.graph import resume_graph, run_graph, thread_for
from app.orchestrator.state import RunState
from app.services import ai_service
from app.services.cards_service import build_cards, held_cards, waiting_cards
from app.services.overrides_service import override_states, review_queue
from app.services.registry_service import Registry
from app.services.review_service import review_all
from app.services.run_output_service import input_hash
from app.services.run_service import Consolidation, build_context, stage
from app.services.upload_service import file_status


class NotReady(Exception):
    """The step cannot run yet. The message says what is missing."""


def invalidate(registry: Registry, run_id: str) -> None:
    """An input changed after the run was analysed, so what it produced describes other inputs. Output is removed and
    the run goes back to 'new': it must be scanned again before anything is reviewed, signed off or exported."""
    if registry.meta(run_id)["status"] == "new":
        return
    registry.update(run_id, status="new", open_items=[], thread=None, blocked=None, checks_passed=None,
                    built=False, generated_for=None, outputs=None, held_decisions={})
    shutil.rmtree(registry.out_dir(run_id), ignore_errors=True)


def _checkpoints(registry: Registry, run_id: str) -> Path:
    return registry.folder(run_id) / "checkpoints.db"


HELD = "journal:"


def _held_pending(registry: Registry, run_id: str, meta: dict[str, Any]) -> list[str]:
    """Journals the rules held ('needs a human') that nobody has decided yet, as 'journal:JE-016'."""
    run = stage(build_context(registry.data_dir(run_id), registry.config_dir(run_id)))
    decided = meta.get("held_decisions", {})
    return [f"{HELD}{d.journal_id}" for d in run.dispositions if d.status == "HOLD" and d.journal_id not in decided]


def _with_held(registry: Registry, run_id: str, meta: dict[str, Any]) -> dict[str, Any]:
    """A finished run still waits while a held journal is undecided: its status goes back to awaiting_review."""
    if meta["status"] not in {"done", "awaiting_review"}:
        return meta
    waiting = [k for k in meta["open_items"] if not k.startswith(HELD)] + _held_pending(registry, run_id, meta)
    if not waiting and meta["status"] == "awaiting_review":
        return registry.update(run_id, status="done", open_items=[])
    return registry.update(run_id, status="awaiting_review" if waiting else "done", open_items=waiting)


def _store(registry: Registry, run_id: str, state: RunState) -> dict[str, Any]:
    meta = registry.update(run_id, status=state["status"], open_items=state.get("open_items", []),
                           blocked=state.get("blocked"), checks_passed=state.get("checks_passed"))
    return _with_held(registry, run_id, meta)


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
    held = {k[len(HELD):]: {"choice": v, "approver": approver} for k, v in decisions.items() if k.startswith(HELD)}
    meta = registry.update(run_id, held_decisions=meta.get("held_decisions", {}) | held)
    chosen = {k: v for k, v in decisions.items() if not k.startswith(HELD)}
    if not chosen:
        return _with_held(registry, run_id, meta)
    answer = {"approver": approver, "decisions": chosen}
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


def journal_memos(run: Consolidation) -> dict[str, dict[str, Any]]:
    """Text addressed to tools (D12), tied to the journal starting last at or before its line."""
    starts = sorted((j.ref.line, j.id) for j in run.ctx.inputs.journals)
    found = {}
    for f in run.findings:
        if f.code == "D12" and f.quoted_text is not None and f.line is not None:
            owner = [jid for line, jid in starts if line <= f.line]
            if owner:
                found[owner[-1]] = {"line": f.line, "text": f.quoted_text.text}
    return found


def review_view(registry: Registry, run_id: str) -> dict[str, Any]:
    ctx = build_context(registry.data_dir(run_id), registry.config_dir(run_id))
    run = stage(ctx)
    states = override_states(load_overrides(registry.config_dir(run_id) / "overrides.toml"), ctx.inputs)
    keep = ("key", "code", "severity", "claim", "file", "line", "action", "subject")
    findings = [{k: v for k, v in f.model_dump(mode="json").items() if k in keep} for f in run.findings]
    dispositions = [d.model_dump(mode="json") for d in run.dispositions]
    open_items = registry.meta(run_id)["open_items"]
    ai = ai_service.review_units(registry, run_id)
    units = ai["units"]
    return {
        "ai": ai, "findings": findings,
        "cards": build_cards(findings, units, dispositions, open_items, journal_memos(run)),
        "dispositions": dispositions,
        "waiting": waiting_cards(states, open_items) + held_cards(dispositions, open_items),
        "queue": review_queue(run.findings, states),
        "open_items": open_items,
        "advice": _advice(registry, run_id),
    }


def generated_now(registry: Registry, run_id: str) -> bool:
    """A Draft was generated for exactly the inputs and config the run holds now (see generate_service)."""
    meta = registry.meta(run_id)
    return meta.get("generated_for") == input_hash(registry.data_dir(run_id), registry.config_dir(run_id))


def require_done(registry: Registry, run_id: str) -> None:
    """Results need output. A run with an item undecided has output only if a Draft was generated on today's inputs,
    and the Draft is labelled as such, so no figure is shown as Determined on an undecided item."""
    meta = registry.meta(run_id)
    if meta["open_items"] and generated_now(registry, run_id):
        return
    if meta["open_items"]:
        raise NotReady("decide these items first: " + ", ".join(meta["open_items"]))
    if meta["status"] != "done":
        raise NotReady("the run has not finished")


def build(registry: Registry, run_id: str) -> dict[str, Any]:
    """The gates are the engine's own invariant and oracle checks, run again on this run's files."""
    require_done(registry, run_id)
    run = stage(build_context(registry.data_dir(run_id), registry.config_dir(run_id)))
    registry.update(run_id, built=True)
    gates = [{"name": c.name, "ok": c.ok, "detail": c.detail} for c in run.checks]
    return {"gates": gates, "passed": run.checks_passed, "blocked": run.blocked, "stages": run_log(registry, run_id)}


_CARDS: dict[tuple[str, int, int], list[dict[str, Any]]] = {}


def result_cards(registry: Registry, run_id: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Cards for a finished run's issues.json rows: the same wording as the review step, with no decision buttons.
    Building them re-runs the engine and the ledger replay (about 70 ms), and the page asks for them on every file it
    shows, so they are kept per run until its issues file or the ledger changes."""
    issues = registry.out_dir(run_id) / "issues.json"
    key = (run_id, issues.stat().st_mtime_ns, load_llm_config().ledger_path.stat().st_mtime_ns)
    if key not in _CARDS:
        run = stage(build_context(registry.data_dir(run_id), registry.config_dir(run_id)))
        units = ai_service.review_units(registry, run_id)["units"]
        dispositions = [d.model_dump(mode="json") for d in run.dispositions]
        _CARDS[key] = build_cards(items, units, dispositions, [], journal_memos(run))
    return _CARDS[key]


def run_log(registry: Registry, run_id: str) -> list[dict[str, Any]]:
    """The stages this run really logged, oldest first, without file paths."""
    events = []
    for path in sorted((registry.folder(run_id) / "logs").glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            events.append({k: v for k, v in row.items() if k not in {"run_id", "data_dir", "folder"}})
    return sorted(events, key=lambda e: str(e["ts"]))
