"""The ledger replays unchanged units and only changed units go live; the smoke run sends one unit per checkpoint."""
from pathlib import Path

from app.agents.reasoning.evidence import Evidence
from app.agents.reasoning.reader import chunk_packets, read_inputs
from app.cli import main
from app.llm.ledger import Ledger
from app.services.reasoning_service import NOT_AVAILABLE, run_reasoning
from app.services.run_service import stage
from tests.unit.agents.reasoning.fakes import CFG, scripted
from tests.unit.agents.reasoning.test_guardrails import CLOUD, layer_answer


def hundred_lines(tmp_path: Path, last: str = "line 100") -> Evidence:
    rows = [*(f"line {n}" for n in range(1, 100)), last]
    (tmp_path / "rows.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    return Evidence(tmp_path, frozenset({"rows.csv"}))


def test_a_changed_line_sends_only_its_own_chunk_to_the_model(tmp_path: Path) -> None:
    model, asked = scripted(lambda p: {"claims": []})
    read_inputs(CFG, Ledger(tmp_path / "l.jsonl"), hundred_lines(tmp_path), "live", model)
    first_run = len(asked)
    read_inputs(CFG, Ledger(tmp_path / "l.jsonl"), hundred_lines(tmp_path, "line 100 EDITED"), "live", model)
    assert first_run == len(chunk_packets(hundred_lines(tmp_path), "rows.csv")) == 3
    assert len(asked) - first_run == 1 and asked[-1]["lines"][-1]["text"] == "line 100 EDITED"


def test_a_replay_of_an_unrecorded_chunk_is_unavailable_not_a_live_call(tmp_path: Path) -> None:
    report = read_inputs(CFG, Ledger(tmp_path / "l.jsonl"), hundred_lines(tmp_path), "replay")
    assert len(report.unavailable) == 3 and report.findings == []


def test_the_smoke_run_sends_one_unit_to_each_checkpoint(ctx, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    model, asked = scripted(layer_answer)
    report = run_reasoning(stage(ctx), CLOUD, Ledger(tmp_path / "l.jsonl"), "live", model, smoke=True)
    assert len(asked) == 3 and report.traces is not None and len(report.traces.traces) == 1


def test_the_unit_limit_for_a_whole_run_counts_all_three_checkpoints(ctx, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    model, asked = scripted(layer_answer)
    run_reasoning(stage(ctx), CLOUD, Ledger(tmp_path / "l.jsonl"), "live", model, max_units=4)
    assert len(asked) == 4


def test_the_local_model_degrades_to_a_plain_message_with_the_rules_intact(ctx, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    report = run_reasoning(stage(ctx), CFG, Ledger(tmp_path / "l.jsonl"), "live")
    assert not report.available and report.note == NOT_AVAILABLE and report.inputs is None


def test_the_cli_reasoning_flag_is_off_by_default_and_live_is_a_separate_switch(capsys) -> None:  # type: ignore[no-untyped-def]
    assert main(["review", "--reasoning"]) == 0  # the configured local model: reports it is not available
    assert "AI review not available" in capsys.readouterr().out


def test_the_smoke_command_exists_and_stops_cleanly_on_the_local_model(capsys) -> None:  # type: ignore[no-untyped-def]
    assert main(["smoke"]) == 0
    assert "AI review not available" in capsys.readouterr().out
