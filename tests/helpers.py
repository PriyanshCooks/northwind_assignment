"""The one way tests run the whole pipeline: the same nodes the command line and the graph use."""
from pathlib import Path

from app.orchestrator.runner_plain import run_plain
from app.orchestrator.state import RunState, initial_state
from app.utils.paths import CONFIG_DIR


def run_pipeline(data_dir: Path, out_dir: Path, db_path: Path, log_dir: Path | None = None) -> RunState:
    state = initial_state(data_dir, out_dir, CONFIG_DIR, db_path, log_dir or db_path.parent / "logs")
    return run_plain(state)
