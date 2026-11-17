"""The eval harness itself, and the rule-based baseline it is measured against. Needs no model. With
NORTHWIND_REQUIRE_LEDGER=1 it also checks that the committed ledger answers every unit."""
import os
import subprocess
import sys

import pytest

from app.domain.runs import Context
from app.llm.factory import load_llm_config
from app.llm.ledger import Ledger
from app.review.grounding import Grounded
from app.review.units import Unit, journal_units, mapping_units
from app.services.review_service import UnitResult, review_all, review_unit
from app.utils.paths import ROOT
from tests.evals.labels import expected
from tests.evals.metrics import score, supplied
from tests.evals.seeds import seeded_journals, seeded_mappings


def result(verified: tuple[str, ...], dropped: tuple[str, ...] = (), unverified: tuple[str, ...] = ()) -> UnitResult:
    grounded = Grounded(verified, tuple((d, "why") for d in dropped), unverified)
    return UnitResult(Unit("journal", "J", {}), "model", grounded)


def test_the_scores_are_plain_set_arithmetic() -> None:
    pairs = [(result(("unbalanced",), dropped=("outside_period",)), {"unbalanced", "exceeds_balance"}),
             (result(("duplicate_of_another",)), set())]
    s = score(pairs)
    assert (s.true_positive, s.false_negative, s.false_positive) == (1, 1, 1)
    assert (s.recall, s.false_alarm_rate, s.ungrounded_rate) == (0.5, 0.5, 1 / 3)
    assert s.exact_units == 0


def test_the_labels_name_the_six_journals_and_the_one_mapping(ctx: Context) -> None:
    labelled = [u.unit_id for u in journal_units(ctx) + mapping_units(ctx) if expected(u.unit_id, u.kind)]
    assert sorted(labelled) == ["JE-006", "JE-009", "JE-014", "JE-016", "JE-017", "JE-019", "UK:2310:12"]


def test_the_rule_based_baseline_finds_every_labelled_defect_without_a_false_alarm(ctx: Context, tmp_path) -> None:  # type: ignore[no-untyped-def]
    cfg, empty = load_llm_config(), Ledger(tmp_path / "none.jsonl")
    results = [review_unit(ctx, cfg, empty, u) for u in journal_units(ctx) + mapping_units(ctx)]
    s = score(supplied(results))
    # the rules read numbers, not wording, so only the lexicon-checked memo claim is missing from JE-006
    assert (s.false_positive, s.false_negative) == (0, 1) and s.recall < 1.0


def test_the_seeded_units_are_labelled_by_construction(ctx: Context) -> None:
    assert len(seeded_journals(ctx)) == 7 and len(seeded_mappings(ctx)) == 8
    assert sum(not s.expected for s in seeded_journals(ctx)) == 1


def test_every_unit_has_a_recorded_answer_when_the_ledger_is_committed(ctx: Context) -> None:
    cfg = load_llm_config()
    if os.environ.get("NORTHWIND_REQUIRE_LEDGER") != "1":
        pytest.skip("set NORTHWIND_REQUIRE_LEDGER=1 once the ledger is complete")
    results = review_all(ctx, cfg, Ledger(cfg.ledger_path))
    assert [r.unit.unit_id for r in results if r.source == "rules"] == []


def test_the_recorder_prints_its_summary_and_exits_with_code_zero() -> None:
    done = subprocess.run([sys.executable, "-m", "tests.evals.record"], cwd=ROOT, capture_output=True, text=True,
                          timeout=300)
    assert done.returncode == 0, done.stderr[-300:]
    assert "answered by the model" in done.stdout
