import json
import subprocess
import sys
from pathlib import Path

from app.orchestrator.graph import resume_graph, run_graph, thread_for
from app.orchestrator.state import RunState, initial_state
from app.utils.paths import CONFIG_DIR, DEFAULT_DATA_DIR, ROOT

TARGET = "mapping:UK:2310"
ANSWER = {"approver": "A. Reviewer", "decisions": {TARGET: "approve"}}


def _config(folder: Path, open_item: bool) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    for name in ("policy.toml", "assumptions.toml", "overrides.toml"):
        text = (CONFIG_DIR / name).read_text(encoding="utf-8")
        if open_item and name == "overrides.toml":
            text = text.replace('status = "approved"', 'status = "open"')
        (folder / name).write_text(text, encoding="utf-8")
    return folder


def _state(root: Path, open_item: bool = False) -> RunState:
    return initial_state(DEFAULT_DATA_DIR, root / "out", _config(root / "config", open_item), root / "run.db",
                         root / "logs")


def test_the_graph_pauses_at_resolve_and_resumes_to_a_finished_run(tmp_path: Path) -> None:
    paused = run_graph(_state(tmp_path / "graph", open_item=True), tmp_path / "graph" / "checkpoints.db")
    assert paused["status"] == "awaiting_review"
    assert not (tmp_path / "graph" / "out").exists()
    resumed = resume_graph(thread_for(DEFAULT_DATA_DIR), ANSWER, tmp_path / "graph" / "checkpoints.db")
    assert resumed["status"] == "done"
    assert resumed["blocked"] is None and resumed["checks_passed"]


def _cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "run.py", *args], cwd=ROOT, capture_output=True, text=True, timeout=120)


def test_a_paused_run_resumes_in_a_separate_process(tmp_path: Path) -> None:
    common = ["--config", str(_config(tmp_path / "config", True)), "--output", str(tmp_path / "out"),
              "--db", str(tmp_path / "run.db")]
    first = _cli("consolidate", *common)
    assert first.returncode == 2 and "paused" in first.stdout and TARGET in first.stdout
    assert not (tmp_path / "out" / "control_figures_pb.json").exists()
    second = _cli("resume", "--thread", thread_for(DEFAULT_DATA_DIR), "--approver", "A. Reviewer", "--approve", TARGET,
                  *common)
    assert second.returncode == 0, second.stdout + second.stderr
    figures = json.loads((tmp_path / "out" / "control_figures_pb.json").read_text(encoding="utf-8"))
    assert figures["group_revenue"] == 28301607.81
    assert 'status = "approved"' in (tmp_path / "config" / "overrides.toml").read_text(encoding="utf-8")
