"""Sign-off on the generated files. A reviewer marks a file reviewed against its hash; if the file changes the mark is
stale. The export is Final only when no problem is open and every exported file is reviewed, otherwise it is a Draft.
The status is written into signoff.json inside the export zip: run_manifest.json is left as the engine wrote it, so the
byte-identical output check still holds."""
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.services import generate_service, output_service, results_service
from app.services.registry_service import Registry

FILE = "signoff.json"
EXPORT_FILE = "signoff.json"
ROW = re.compile(r"^\d+:\d+$")  # section index and row index in the file view


def _load(folder: Path) -> list[dict[str, Any]]:
    path = folder / FILE
    return list(json.loads(path.read_text(encoding="utf-8"))) if path.is_file() else []


def _exported(registry: Registry, run_id: str) -> list[dict[str, Any]]:
    """The files that will be in the zip, with their current hash."""
    listing = output_service.file_list(registry.out_dir(run_id))
    chosen = registry.meta(run_id)["outputs"]
    return [f for f in listing if not chosen or f["name"] in chosen or f["name"] == results_service.ALWAYS]


def status(registry: Registry, run_id: str) -> dict[str, Any]:
    entries = _load(registry.folder(run_id))
    marks = {m["file"]: m for m in entries if "row" not in m}  # the newest mark per file
    files = []
    for f in _exported(registry, run_id):
        mark = marks.get(f["name"])
        same = [m for m in entries if m["file"] == f["name"] and m["sha256"] == f["sha256"]]
        rows = sorted({m["row"] for m in same if m.get("row")})
        state = "open" if mark is None else "reviewed" if mark["sha256"] == f["sha256"] else "stale"
        files.append({"name": f["name"], "sha256": f["sha256"], "state": state,
                      "reviewed_by": mark["reviewer"] if mark else None, "at": mark["at"] if mark else None,
                      "rows_reviewed": rows})
    left = generate_service.unanswered(registry, run_id)
    reasons = []
    if left["problems"]:
        reasons.append(f"{left['problems']} problem(s) in the inputs are still unanswered")
    waiting = [f["name"] for f in files if f["state"] != "reviewed"]
    if waiting:
        reasons.append(f"{len(waiting)} output file(s) not reviewed: " + ", ".join(waiting))
    return {"files": files, "problems": left["problems"], "status": "Draft" if reasons else "Final", "reasons": reasons}


def mark(registry: Registry, run_id: str, name: str, reviewer: str, row: str | None = None) -> dict[str, Any]:
    if not reviewer.strip():
        raise ValueError("enter your name before you mark a file reviewed")
    current = {f["name"]: f for f in _exported(registry, run_id)}
    if name not in current:
        raise ValueError(f"not an exported file of this run: {name}")
    if row is not None and not ROW.match(row):
        raise ValueError(f"not a row of a file view: {row}")
    entry = {"file": name, "sha256": current[name]["sha256"], "reviewer": reviewer.strip(),
             "at": datetime.now(UTC).isoformat(), **({"row": row} if row else {})}
    folder = registry.folder(run_id)
    (folder / FILE).write_text(json.dumps([*_load(folder), entry], indent=2), encoding="utf-8")
    return status(registry, run_id)


def export_document(registry: Registry, run_id: str) -> bytes:
    """What goes into the zip beside the chosen files: the status, why it is a Draft, and who reviewed each file."""
    now = status(registry, run_id)
    document = {"run": run_id, "status": now["status"], "reasons": now["reasons"], "files": now["files"]}
    return json.dumps(document, indent=2).encode("utf-8")
