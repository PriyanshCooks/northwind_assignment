import json
from pathlib import Path

from app.services.run_service import run_consolidation
from app.utils.logging import RunLogger
from app.utils.paths import DEFAULT_DATA_DIR


def lines(path: Path | None) -> list[dict[str, object]]:
    assert path is not None
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_logger_writes_one_json_object_per_event_with_run_stage_and_event(tmp_path: Path) -> None:
    log = RunLogger(tmp_path, "abc123")
    log.event("analyse", "finding", finding_key="D03:adjustments.json:102:balance")
    log.close()
    (entry,) = lines(log.path)
    assert (entry["run_id"], entry["stage"], entry["event"]) == ("abc123", "analyse", "finding")
    assert entry["finding_key"] == "D03:adjustments.json:102:balance" and "ts" in entry


def test_one_run_produces_a_readable_log_with_gate_results_and_finding_keys(tmp_path: Path) -> None:
    run = run_consolidation(DEFAULT_DATA_DIR, tmp_path / "out", tmp_path / "run.db", tmp_path / "logs")
    events = lines(run.log_path)
    stages = {str(e["stage"]) for e in events}
    assert {"intake", "analyse", "consolidate", "verify", "export", "run"} <= stages
    assert sum(1 for e in events if e["event"] == "gate") == 20
    assert any(e.get("finding_key") == "D12:adjustments.json:112:text" for e in events)
    assert all("run_id" in e for e in events)


def test_two_runs_give_identical_outputs_but_different_logs(tmp_path: Path) -> None:
    first = run_consolidation(DEFAULT_DATA_DIR, tmp_path / "a", tmp_path / "a.db", tmp_path / "logs")
    second = run_consolidation(DEFAULT_DATA_DIR, tmp_path / "b", tmp_path / "b.db", tmp_path / "logs")
    for path in (tmp_path / "a").iterdir():
        assert path.read_bytes() == (tmp_path / "b" / path.name).read_bytes()
    assert first.log_path != second.log_path
    assert first.log_path is not None and second.log_path is not None
    assert first.log_path.read_text(encoding="utf-8") != second.log_path.read_text(encoding="utf-8")


def test_no_timestamp_from_the_log_appears_in_any_output(tmp_path: Path) -> None:
    run = run_consolidation(DEFAULT_DATA_DIR, tmp_path / "out", tmp_path / "run.db", tmp_path / "logs")
    stamp = str(lines(run.log_path)[0]["ts"])[:16]
    for path in (tmp_path / "out").iterdir():
        assert stamp not in path.read_text(encoding="utf-8")
