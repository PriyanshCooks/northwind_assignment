"""A credit-balance account holds a negative number here; the record says so and the false sign concerns go."""
import json
from pathlib import Path

import pytest

from app.agents.reasoning.calc_review import review_calculations
from app.agents.reasoning.evidence import Evidence
from app.domain.runs import Context
from app.llm.ledger import Ledger
from app.services.reasoning_service import build_evidence
from app.services.run_service import stage
from tests.unit.agents.reasoning.fakes import CFG, scripted


@pytest.fixture(scope="module")
def evidence(ctx: Context) -> Evidence:
    return build_evidence(stage(ctx))


def test_a_row_record_states_its_normal_side_and_how_amounts_are_stored(evidence: Evidence) -> None:
    revenue, cash = json.loads(evidence.calculations["row:4100"]), json.loads(evidence.calculations["row:1100"])
    assert (revenue["normal_side"], cash["normal_side"]) == ("credit", "debit")
    assert "debit-positive" in revenue["storage"] and "negative" in revenue["storage"]


def test_a_figure_record_has_no_side_and_a_flipped_total_says_so(evidence: Evidence) -> None:
    revenue = json.loads(evidence.calculations["fig:group_revenue"])
    assert revenue["normal_side"] is None and "sign-flipped" in revenue["storage"]


def test_every_credit_balance_revenue_row_is_on_its_normal_side_on_the_sample(evidence: Evidence) -> None:
    assert evidence.results["row:4100"] < 0 and evidence.normal_sides["row:4100"] == "credit"


def test_sign_concerns_on_normal_balances_are_dropped_and_only_real_ones_remain(evidence: Evidence,
                                                                                 tmp_path: Path) -> None:
    negative = [c for c in evidence.normal_sides if evidence.results[c] < 0]
    wrong = {c for c in negative if evidence.normal_sides[c] == "debit"}
    assert len(negative) > len(wrong), "the sample must hold credit-balance rows"

    def claim(calc_id: str) -> dict[str, object]:
        return {"cite": calc_id, "concern": "sign_implausible", "reason": "negative", "quoted": []}

    model, _ = scripted(lambda p: {"claims": [claim(p["calculation_id"])] if p["calculation_id"] in negative else []})
    report = review_calculations(CFG, Ledger(tmp_path / "l.jsonl"), evidence, "live", model)
    assert {f.cite for f in report.findings} == wrong
    assert len(report.dropped) == len(negative) - len(wrong)
    assert all("normal credit side" in d.why for d in report.dropped)
