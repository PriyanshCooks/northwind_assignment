"""Scan progress for one run, read from its run log: the 'file scanned' events the analyse stage wrote. Nothing is
estimated. A file with no event yet is waiting; once the 'findings' event is logged the scan is finished."""
import json
from pathlib import Path
from typing import Any

from app.services.registry_service import Registry
from app.services.upload_service import EXPECTED_FILES


def _newest_log(folder: Path) -> Path | None:
    logs = sorted((folder / "logs").glob("*.jsonl"), key=lambda p: p.stat().st_mtime_ns)
    return logs[-1] if logs else None


def _events(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def progress(registry: Registry, run_id: str) -> dict[str, Any]:
    folder = registry.folder(run_id)
    events = [e for e in _events(_newest_log(folder)) if e.get("stage") == "analyse"]
    scanned = {e["file"]: e["findings"] for e in events if e["event"] == "file scanned"}
    finished = any(e["event"] == "findings" for e in events)
    files = []
    for name in sorted(EXPECTED_FILES):
        if not (registry.data_dir(run_id) / name).is_file():
            files.append({"name": name, "status": "missing", "findings": None})
        else:
            files.append({"name": name, "status": "scanned" if name in scanned else "waiting",
                          "findings": scanned.get(name)})
    done = sum(1 for f in files if f["status"] == "scanned")
    return {"files": files, "scanned": done, "total": sum(1 for f in files if f["status"] != "missing"),
            "finished": finished, "status": registry.meta(run_id)["status"]}
