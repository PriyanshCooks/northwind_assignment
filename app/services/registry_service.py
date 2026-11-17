"""The run registry: one folder per run under .northwind/runs/<id>/ holding its own data, config, outputs and logs.
Config is copied per run so an approval written by one run never changes the repository's overrides.toml."""
import json
import re
import secrets
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.orchestrator.state import RunState, initial_state
from app.utils.paths import CONFIG_DIR, DEFAULT_DATA_DIR

RUN_ID = re.compile(r"^r\d{8}-\d{6}-[0-9a-f]{4}$")
CONFIG_COPIED = ("policy.toml", "assumptions.toml", "overrides.toml", "bundle_manifest.sha256")


class UnknownRun(Exception):
    pass


class Registry:
    def __init__(self, root: Path) -> None:
        self.root = root

    def folder(self, run_id: str) -> Path:
        """The id is checked against a strict pattern before it touches the file system."""
        if not RUN_ID.match(run_id) or not (self.root / run_id / "run.json").is_file():
            raise UnknownRun(run_id)
        return self.root / run_id

    def data_dir(self, run_id: str) -> Path:
        return self.folder(run_id) / "data"

    def config_dir(self, run_id: str) -> Path:
        return self.folder(run_id) / "config"

    def out_dir(self, run_id: str) -> Path:
        return self.folder(run_id) / "output"

    def meta(self, run_id: str) -> dict[str, Any]:
        return dict(json.loads((self.folder(run_id) / "run.json").read_text(encoding="utf-8")))

    def update(self, run_id: str, **fields: Any) -> dict[str, Any]:
        meta = self.meta(run_id) | fields
        (self.folder(run_id) / "run.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        return meta

    def create(self, name: str = "", use_sample: bool = False, parent: str | None = None,
               copy_data_from: Path | None = None, copy_config_from: Path = CONFIG_DIR) -> dict[str, Any]:
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        run_id = f"r{stamp}-{secrets.token_hex(2)}"
        folder = self.root / run_id
        (folder / "data").mkdir(parents=True)
        (folder / "config").mkdir()
        for name_ in CONFIG_COPIED:
            shutil.copy2(copy_config_from / name_, folder / "config" / name_)
        source = copy_data_from or (DEFAULT_DATA_DIR if use_sample else None)
        if source is not None:
            shutil.copytree(source, folder / "data", dirs_exist_ok=True)
        meta: dict[str, Any] = {"id": run_id, "name": name.strip() or run_id, "created": datetime.now(UTC).isoformat(),
                "parent": parent, "status": "new", "open_items": [], "thread": None, "outputs": None}
        (folder / "run.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        return meta

    def list(self, archived: bool = False) -> list[dict[str, Any]]:
        """Runs in use, or with archived=True the archived ones. Archiving hides a run; nothing is deleted."""
        found = [self.meta(p.name) for p in self.root.glob("r*") if RUN_ID.match(p.name) and (p / "run.json").is_file()]
        shown = [m for m in found if bool(m.get("archived")) == archived]
        return sorted(shown, key=lambda m: str(m["created"]), reverse=True)

    def state(self, run_id: str) -> RunState:
        folder = self.folder(run_id)
        return initial_state(folder / "data", folder / "output", folder / "config", folder / "run.db",
                             folder / "logs")
