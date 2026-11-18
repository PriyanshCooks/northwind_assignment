"""The explain step: it writes a why and a trace for a finding the rules already raised, grounded like the
investigator, and nothing about the finding changes."""
from pathlib import Path

import pytest

from app.domain.runs import Context
from app.llm.ledger import Ledger
from app.reasoning.explain import explain_findings
from app.services.reasoning_service import build_evidence
from app.services.run_service import Consolidation, stage
from tests.unit.reasoning.fakes import CFG
from tests.unit.reasoning.test_checkpoints import tool_model


@pytest.fixture(scope="module")
def run(ctx: Context) -> Consolidation:
    return stage(ctx)


def test_the_why_and_trace_are_grounded_and_the_finding_is_unchanged(run: Consolidation, tmp_path: Path) -> None:
    finding = next(f for f in run.findings if f.code == "D02" and f.file == "map_uk.csv" and f.line == 12)
    before = list(run.findings)
    final = {"chain": [{"cite": "map_uk.csv:12", "note": "the map row", "quoted": ["Deferred income"]},
                       {"cite": "map_uk.csv:999", "note": "invented", "quoted": []}],
             "cause": "a liability sits in revenue; the balance is 313131"}
    model, seen = tool_model([("read_lines", {"file": "map_uk.csv", "start": 12, "end": 12})], final)
    report = explain_findings(CFG, Ledger(tmp_path / "l.jsonl"), build_evidence(run), [finding], "live", model)
    result = report.explained[finding.key]
    assert [c for c, _ in result.chain] == ["map_uk.csv:12"] and len(result.dropped) == 1
    assert result.cause == ""  # 313131 appears nowhere the model saw
    assert run.findings == before and len(seen) == 1

