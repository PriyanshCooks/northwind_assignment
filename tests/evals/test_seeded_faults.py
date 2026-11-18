"""The seeded-fault harness: faults are planted where they say, the scoring counts hits, misses and false alarms,
and nothing the rules concluded reaches a packet. Fake models only; the live run is a separate command."""
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from app.llm.ledger import Ledger
from app.utils.paths import DEFAULT_DATA_DIR
from tests.evals.seeded_faults import FAULTS, evaluate, plant, summary
from tests.unit.agents.reasoning.fakes import CFG, scripted


@pytest.fixture(scope="module")
def cites(tmp_path_factory: pytest.TempPathFactory) -> dict[str, set[str]]:
    return plant(tmp_path_factory.mktemp("plant") / "data")


def claims_on(lines: set[str], extra: frozenset[str] = frozenset()) -> Any:
    """A model that flags exactly these lines in whichever chunk shows them, and nothing in calculations."""
    def answer(packet: dict[str, Any]) -> dict[str, Any]:
        if "calculation_id" in packet:
            return {"claims": []}
        shown = [x["line"] for x in packet["lines"] if x["line"] in lines | extra]
        return {"claims": [{"cite": c, "flag": "value_not_plausible", "reason": "looks wrong", "quoted": []}
                           for c in shown]}
    return answer


def digest(folder: Path) -> dict[str, str]:
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.iterdir())}


def test_six_faults_are_planted_and_the_supplied_data_is_untouched(tmp_path: Path, cites: dict[str, set[str]]) -> None:
    before = digest(DEFAULT_DATA_DIR)
    again = plant(tmp_path / "data")
    assert digest(DEFAULT_DATA_DIR) == before and again == cites
    assert len(FAULTS) == 6 and all(cites[f.name] for f in FAULTS)
    changed = {c.split(":")[0] for lines in cites.values() for c in lines}
    assert changed == {"fx_rates.csv", "adjustments.json", "map_uk.csv", "tb_uk.csv", "intercompany.csv"}


def test_a_model_that_flags_every_fault_hits_six_with_no_false_alarms(tmp_path: Path,
                                                                      cites: dict[str, set[str]]) -> None:
    model, _ = scripted(claims_on(set().union(*cites.values())))
    result = evaluate(tmp_path, CFG, Ledger(tmp_path / "l.jsonl"), "live", model)
    assert result["hits"] == 6 and result["false_alarms"] == 0
    assert result["rules"]["rate x100"] == ["D15"]  # type: ignore[index]
    assert summary(result)[-1] == "6 of 6 hit, 0 missed, 0 false alarms"


def test_a_model_that_flags_nothing_misses_all_six(tmp_path: Path) -> None:
    model, _ = scripted(claims_on(set()))
    result = evaluate(tmp_path, CFG, Ledger(tmp_path / "l.jsonl"), "live", model)
    assert result["hits"] == 0 and result["false_alarms"] == 0
    assert all(f["result"] == "miss" for f in result["faults"].values())  # type: ignore[attr-defined]


def test_a_flag_on_a_clean_line_is_a_false_alarm_and_one_fault_missed(tmp_path: Path,
                                                                       cites: dict[str, set[str]]) -> None:
    flagged = set().union(*(v for k, v in cites.items() if k != "rate x100"))
    model, _ = scripted(claims_on(flagged, frozenset({"tb_us.csv:2"})))
    result = evaluate(tmp_path, CFG, Ledger(tmp_path / "l.jsonl"), "live", model)
    assert result["faults"]["rate x100"]["result"] == "miss"  # type: ignore[index]
    assert result["hits"] == 5 and result["false_alarm_cites"] == ["tb_us.csv:2"]


def test_no_rule_finding_or_verdict_is_in_any_packet(tmp_path: Path, cites: dict[str, set[str]]) -> None:
    model, asked = scripted(claims_on(set()))
    evaluate(tmp_path, CFG, Ledger(tmp_path / "l.jsonl"), "live", model)
    text = json.dumps(asked)
    assert asked and not any(word in text for word in ("D15", "D02", "D12", "severity", "verdict", "finding"))
    assert {tuple(sorted(p)) for p in asked if "lines" in p} == {
        ("context_line_numbers_before", "file", "lines", "meaning")}
    assert {tuple(sorted(p)) for p in asked if "calculation_id" in p} == {("calculation_id", "record")}
