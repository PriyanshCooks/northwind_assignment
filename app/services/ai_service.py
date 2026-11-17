"""What the recorded AI review did, unit by unit, replayed from the ledger. No model is called: a unit with no recorded
answer is shown as rules-only. The review is advice (policy 2) and changes no figure."""
import json
from decimal import Decimal
from typing import Any

from app.llm.factory import load_llm_config
from app.llm.ledger import Ledger
from app.services.registry_service import Registry
from app.services.review_service import UnitResult, review_all
from app.services.run_service import build_context

AGENT = {"journal": "journal_reviewer", "mapping": "mapping_reviewer"}


def _same(packet: dict[str, Any]) -> str:
    return json.dumps(packet, sort_keys=True, default=str)


def _recorded(ledger: Ledger) -> dict[tuple[str, str], dict[str, Any]]:
    """The newest validated ledger entry for each (agent, packet); the replay key also holds the prompt version."""
    return {(e["agent"], _same(e["packet"])): e for e in ledger.entries.values() if e.get("validated")}


def _plain_why(why: str) -> str:
    return why.replace("the packet", "the supplied data")


def _unit(r: UnitResult, entry: dict[str, Any] | None) -> dict[str, Any]:
    usage = (entry or {}).get("usage") or {}
    return {
        "kind": r.unit.kind, "unit": r.unit.unit_id, "source": r.source, "recorded": r.source == "model",
        "packet": r.unit.packet, "answer": entry["response"] if entry and r.source == "model" else None,
        "verified": list(r.grounded.verified), "unverified": list(r.grounded.unverified),
        "dropped": [{"claim": c, "why": _plain_why(w)} for c, w in r.grounded.dropped], "missed": list(r.missed),
        "input_tokens": usage.get("input_tokens"), "output_tokens": usage.get("output_tokens"),
        "cost_usd": entry.get("cost_usd") if entry else None, "note": r.note,
    }


def _totals(units: list[dict[str, Any]]) -> dict[str, Any]:
    got = [u for u in units if u["recorded"]]
    priced = [Decimal(u["cost_usd"]) for u in got if u["cost_usd"] is not None]
    return {
        "units": len(units), "units_with_recorded_answer": len(got),
        "claims": sum(len(u["verified"]) + len(u["unverified"]) + len(u["dropped"]) for u in got),
        "verified": sum(len(u["verified"]) for u in got), "dropped": sum(len(u["dropped"]) for u in got),
        "input_tokens": sum(u["input_tokens"] or 0 for u in got),
        "output_tokens": sum(u["output_tokens"] or 0 for u in got),
        "cost_usd": str(sum(priced, Decimal(0))) if got and len(priced) == len(got) else None,
        "cost_note": "estimate from config/pricing.toml" if len(priced) == len(got) else "some calls have no price",
    }


def review_units(registry: Registry, run_id: str) -> dict[str, Any]:
    ctx = build_context(registry.data_dir(run_id), registry.config_dir(run_id))
    cfg = load_llm_config()
    ledger = Ledger(cfg.ledger_path)
    index = _recorded(ledger)
    units = [_unit(r, index.get((AGENT[r.unit.kind], _same(r.unit.packet))))
             for r in review_all(ctx, cfg, ledger, "replay")]
    return {"label": "recorded review", "model": cfg.model, "ledger": cfg.ledger, "units": units,
            "totals": _totals(units)}
