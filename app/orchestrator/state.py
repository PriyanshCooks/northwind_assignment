"""The run state: paths, hashes, status and open item keys. No tables or amounts: those are rebuilt."""
from pathlib import Path
from typing import TypedDict


class RunState(TypedDict, total=False):
    data_dir: str
    out_dir: str
    config_dir: str
    db_path: str
    log_dir: str
    log_file: str
    run_id: str
    status: str
    open_items: list[str]
    decided: list[str]
    blocked: str | None
    checks_passed: bool
    output_hashes: dict[str, str]


def initial_state(data_dir: Path, out_dir: Path, config_dir: Path, db_path: Path, log_dir: Path) -> RunState:
    return RunState(
        data_dir=str(data_dir), out_dir=str(out_dir), config_dir=str(config_dir), db_path=str(db_path),
        log_dir=str(log_dir), status="new", open_items=[], decided=[],
    )
