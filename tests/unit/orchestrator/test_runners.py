import json
import subprocess
import sys
from pathlib import Path

from app.orchestrator.graph import resume_graph, run_graph, thread_for
from app.orchestrator.runner_plain import run_plain
from app.orchestrator.state import RunState, initial_state
from app.services.run_service import input_hash
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
    resumed = resume_graph(thread_for(DEFAULT_DATA_DIR, tmp_path / "graph" / "config"), ANSWER,
                          tmp_path / "graph" / "checkpoints.db")
    assert resumed["status"] == "done"
    assert resumed["blocked"] is None and resumed["checks_passed"]


def _cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "run.py", *args], cwd=ROOT, capture_output=True, text=True, timeout=120)


def test_both_runners_write_identical_outputs(tmp_path: Path) -> None:
    plain = run_plain(_state(tmp_path / "plain"))
    graph = run_graph(_state(tmp_path / "graph"), tmp_path / "graph" / "checkpoints.db")
    assert plain["status"] == graph["status"] == "done"
    assert plain["output_hashes"] == graph["output_hashes"]
    assert "run_manifest.json" in plain["output_hashes"]


def test_an_open_override_stops_the_plain_runner_before_any_output(tmp_path: Path) -> None:
    state = run_plain(_state(tmp_path, open_item=True))
    assert (state["status"], state["open_items"]) == ("awaiting_review", [TARGET])
    assert not (tmp_path / "out").exists()


def test_a_resumed_graph_and_an_answered_plain_run_agree_byte_for_byte(tmp_path: Path) -> None:
    run_graph(_state(tmp_path / "graph", open_item=True), tmp_path / "graph" / "checkpoints.db")
    resumed = resume_graph(thread_for(DEFAULT_DATA_DIR, tmp_path / "graph" / "config"), ANSWER,
                          tmp_path / "graph" / "checkpoints.db")
    plain = run_plain(_state(tmp_path / "plain", open_item=True), ANSWER)
    assert resumed["output_hashes"] == plain["output_hashes"]


def test_the_cli_engines_print_the_same_figures(tmp_path: Path) -> None:
    graph = _cli("consolidate", "--output", str(tmp_path / "g"), "--db", str(tmp_path / "g.db" / "run.db"))
    plain = _cli("consolidate", "--engine", "plain", "--output", str(tmp_path / "p"),
                 "--db", str(tmp_path / "p.db" / "run.db"))
    assert graph.returncode == plain.returncode == 0
    assert graph.stdout.splitlines()[1:] == plain.stdout.splitlines()[1:]


def test_a_paused_run_resumes_in_a_separate_process(tmp_path: Path) -> None:
    common = ["--config", str(_config(tmp_path / "config", True)), "--output", str(tmp_path / "out"),
              "--db", str(tmp_path / "run.db")]
    first = _cli("consolidate", *common)
    assert first.returncode == 2 and "paused" in first.stdout and TARGET in first.stdout
    assert not (tmp_path / "out" / "control_figures_pb.json").exists()
    thread = thread_for(DEFAULT_DATA_DIR, tmp_path / "config")
    second = _cli("resume", "--thread", thread, "--approver", "A. Reviewer", "--approve", TARGET,
                  *common)
    assert second.returncode == 0, second.stdout + second.stderr
    figures = json.loads((tmp_path / "out" / "control_figures_pb.json").read_text(encoding="utf-8"))
    assert figures["group_revenue"] == 28301607.81
    assert 'status = "approved"' in (tmp_path / "config" / "overrides.toml").read_text(encoding="utf-8")


def test_approving_an_override_changes_the_run_id_and_the_thread(tmp_path: Path) -> None:
    open_cfg = _config(tmp_path / "open", open_item=True)
    approved_cfg = _config(tmp_path / "approved", open_item=False)
    assert input_hash(DEFAULT_DATA_DIR, open_cfg) != input_hash(DEFAULT_DATA_DIR, approved_cfg)
    assert thread_for(DEFAULT_DATA_DIR, open_cfg) != thread_for(DEFAULT_DATA_DIR, approved_cfg)


def test_a_paused_thread_is_not_reused_once_the_override_is_approved(tmp_path: Path) -> None:
    checkpoints = tmp_path / "checkpoints.db"
    paused = run_graph(_state(tmp_path / "a", open_item=True), checkpoints)
    assert paused["status"] == "awaiting_review"
    finished = run_graph(_state(tmp_path / "b", open_item=False), checkpoints)
    assert finished["status"] == "done"
    assert finished["run_id"] != paused["run_id"]
