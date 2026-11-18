"""Checkpoints 2 and 3 with fake models: grounding, the tool caps, the recorded trail, the unit limit."""
import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from pydantic_ai import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.agents.reasoning.budget import UnitBudget
from app.agents.reasoning.calc_review import review_calculations
from app.agents.reasoning.evidence import Evidence
from app.agents.reasoning.investigator import investigate
from app.domain.runs import Context
from app.llm.ledger import Ledger, LlmStop
from app.services.reasoning_service import build_evidence, policy_rules
from app.services.run_service import stage
from tests.unit.agents.reasoning.fakes import CFG, scripted

GOODWILL = "fig:goodwill_closing"


@pytest.fixture(scope="module")
def evidence(ctx: Context) -> Evidence:
    return build_evidence(stage(ctx))


def concern(cite: str, kind: str = "sign_implausible", reason: str = "looks wrong",
            quoted: list[str] | None = None) -> Any:
    return {"cite": cite, "concern": kind, "reason": reason, "quoted": quoted or []}


def about(calc_id: str, *claims: Any) -> Any:
    return lambda p: {"claims": list(claims) if p["calculation_id"] == calc_id else []}


def test_the_evidence_holds_a_record_for_every_row_and_figure_and_the_policy_clauses(evidence: Evidence) -> None:
    assert GOODWILL in evidence.calculations and "row:1100" in evidence.calculations
    assert "closing rate" in evidence.rules["policy 2"]
    assert "acquisition_note.md:" in evidence.lineage[GOODWILL]


def test_policy_clauses_are_split_by_number() -> None:
    clauses = policy_rules("1. one\n2. two\n   - more\n3. three")
    assert clauses == {"policy 1": "one", "policy 2": "two\n   - more", "policy 3": "three"}


def test_a_concern_the_code_cannot_check_is_only_a_suspicion(evidence: Evidence, tmp_path: Path) -> None:
    model, _ = scripted(about("fig:total_assets", concern("fig:total_assets", "magnitude_implausible")))
    report = review_calculations(CFG, Ledger(tmp_path / "a.jsonl"), evidence, "live", model)
    assert [(f.cite, f.tier) for f in report.findings] == [("fig:total_assets", "suspicion")]


def test_a_sign_concern_on_a_negative_nonnegative_figure_is_verified(evidence: Evidence, tmp_path: Path) -> None:
    negative = replace(evidence, results={**evidence.results, "fig:total_assets": Decimal(-1)})
    model, _ = scripted(about("fig:total_assets", concern("fig:total_assets")))
    report = review_calculations(CFG, Ledger(tmp_path / "a.jsonl"), negative, "live", model)
    assert [f.tier for f in report.findings] == ["verified"]


def test_a_claim_about_another_record_or_with_an_invented_number_is_dropped(evidence: Evidence, tmp_path: Path) -> None:
    model, _ = scripted(about("fig:total_assets", concern("fig:group_profit"),
                              concern("fig:total_assets", reason="it should be 9876543")))
    report = review_calculations(CFG, Ledger(tmp_path / "a.jsonl"), evidence, "live", model)
    assert report.findings == [] and len(report.dropped) == 2


def test_the_unit_limit_counts_live_units_and_stops_the_run(evidence: Evidence, tmp_path: Path) -> None:
    model, asked = scripted(lambda p: {"claims": []})
    report = review_calculations(CFG, Ledger(tmp_path / "a.jsonl"), evidence, "live", model, UnitBudget(limit=3))
    assert len(asked) == 3 and report.stopped_early


def test_replayed_units_do_not_count_against_the_limit(evidence: Evidence, tmp_path: Path) -> None:
    model, asked = scripted(lambda p: {"claims": []})
    review_calculations(CFG, Ledger(tmp_path / "a.jsonl"), evidence, "live", model, UnitBudget(limit=3))
    again = review_calculations(CFG, Ledger(tmp_path / "a.jsonl"), evidence, "live", model, UnitBudget(limit=3))
    assert len(asked) == 6 and again.stopped_early  # the first 3 replayed free, then 3 more went live


def tool_model(calls: list[tuple[str, dict[str, Any]]], final: dict[str, Any]) -> tuple[FunctionModel, list[str]]:
    """Calls each tool in turn, then answers. `seen` collects what the tools returned."""
    seen: list[str] = []

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        returned = [p for m in messages for p in m.parts if p.part_kind == "tool-return"]
        seen[:] = [str(p.content) for p in returned]  # type: ignore[attr-defined]
        if len(returned) < len(calls) and info.function_tools:  # a spent toolbox hides its tools
            name, args = calls[len(returned)]
            return ModelResponse(parts=[ToolCallPart(name, args)])
        return ModelResponse(parts=[TextPart(json.dumps(final))])

    return FunctionModel(respond), seen


def flagged(evidence: Evidence, tmp_path: Path) -> Any:
    model, _ = scripted(about(GOODWILL, concern(GOODWILL, "magnitude_implausible")))
    return review_calculations(CFG, Ledger(tmp_path / "cp2.jsonl"), evidence, "live", model)


def test_the_investigator_follows_a_figure_to_its_source_lines(evidence: Evidence, tmp_path: Path) -> None:
    final = {"chain": [{"cite": GOODWILL, "note": "built from the acquisition note", "quoted": []},
                       {"cite": "acquisition_note.md:4", "note": "consideration", "quoted": ["690,000,000"]}],
             "cause": "consideration is INR 690,000,000"}
    model, seen = tool_model([("get_calculation", {"calc_id": GOODWILL}), ("get_lineage", {"row_id": GOODWILL})], final)
    report = investigate(CFG, Ledger(tmp_path / "cp3.jsonl"), evidence, flagged(evidence, tmp_path), "live", model)
    trace = report.traces[0]
    assert [c for c, _ in trace.chain] == [GOODWILL, "acquisition_note.md:4"] and not trace.dropped
    assert [t["tool"] for t in trace.trail] == ["get_calculation", "get_lineage"] and len(seen) == 2


def test_the_trail_is_recorded_with_the_answer_and_replays_with_no_model(evidence: Evidence, tmp_path: Path) -> None:
    model, _ = tool_model([("get_rule", {"name": "policy 4"})], {"chain": [], "cause": "see policy 4"})
    first = investigate(CFG, Ledger(tmp_path / "cp3.jsonl"), evidence, flagged(evidence, tmp_path), "live", model)
    again = investigate(CFG, Ledger(tmp_path / "cp3.jsonl"), evidence, flagged(evidence, tmp_path), "replay")
    assert again.traces[0].trail == first.traces[0].trail and again.traces[0].trail[0]["tool"] == "get_rule"
    assert '"trail"' in (tmp_path / "cp3.jsonl").read_text(encoding="utf-8")


def test_a_sixth_tool_call_is_refused_and_the_run_still_ends(evidence: Evidence, tmp_path: Path) -> None:
    calls = [("read_lines", {"file": "tb_uk.csv", "start": n, "end": n}) for n in range(1, 8)]
    model, seen = tool_model(calls, {"chain": [], "cause": ""})
    report = investigate(CFG, Ledger(tmp_path / "cp3.jsonl"), evidence, flagged(evidence, tmp_path), "live", model)
    assert len(report.traces[0].trail) == 5 and len(seen) == 5  # the tools are withdrawn, so the model answers


def test_a_repeated_call_is_refused_but_not_recorded_twice(evidence: Evidence, tmp_path: Path) -> None:
    same = ("get_rule", {"name": "policy 4"})
    model, seen = tool_model([same, same], {"chain": [], "cause": ""})
    report = investigate(CFG, Ledger(tmp_path / "cp3.jsonl"), evidence, flagged(evidence, tmp_path), "live", model)
    assert len(report.traces[0].trail) == 1 and "already made" in seen[1]


def test_a_step_citing_a_missing_line_or_an_unseen_number_is_dropped(evidence: Evidence, tmp_path: Path) -> None:
    final = {"chain": [{"cite": "acquisition_note.md:99", "note": "x", "quoted": []},
                       {"cite": GOODWILL, "note": "the value was 424242", "quoted": []}], "cause": "it is 313131"}
    model, _ = tool_model([], final)
    report = investigate(CFG, Ledger(tmp_path / "cp3.jsonl"), evidence, flagged(evidence, tmp_path), "live", model)
    trace = report.traces[0]
    assert trace.chain == () and len(trace.dropped) == 2 and trace.cause == ""


def test_only_concerns_are_investigated(evidence: Evidence, tmp_path: Path) -> None:
    model, _ = scripted(lambda p: {"claims": []})
    calc = review_calculations(CFG, Ledger(tmp_path / "a.jsonl"), evidence, "live", model, UnitBudget(limit=2))
    assert investigate(CFG, Ledger(tmp_path / "b.jsonl"), evidence, calc, "live", model).traces == []


def test_five_failed_investigations_in_a_row_trip_the_breaker(evidence: Evidence, tmp_path: Path) -> None:
    broken = FunctionModel(lambda m, i: ModelResponse(parts=[TextPart("not json")]))
    many = flagged(evidence, tmp_path)
    many.findings = [replace(many.findings[0], cite=k) for k in list(evidence.calculations)[:7]]
    with pytest.raises(LlmStop, match="circuit breaker"):
        investigate(CFG, Ledger(tmp_path / "cp3.jsonl"), evidence, many, "live", broken)


def test_a_model_that_keeps_calling_tools_after_refusals_still_gets_to_answer(evidence: Evidence,
                                                                               tmp_path: Path) -> None:
    calls = [("read_lines", {"file": "tb_uk.csv", "start": n, "end": n}) for n in range(1, 11)]
    model, seen = tool_model(calls, {"chain": [], "cause": ""})
    report = investigate(CFG, Ledger(tmp_path / "cp3.jsonl"), evidence, flagged(evidence, tmp_path), "live", model)
    assert len(report.traces[0].trail) == 5 and len(seen) == 5
