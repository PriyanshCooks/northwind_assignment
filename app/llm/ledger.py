"""The ledger: every model call, one JSON line each, in ledger/<model>.jsonl. A run replays from it, so a fresh clone
gives the same answers offline. The local model is not repeatable, so this file is the only source of determinism."""
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from app.utils.hashing import json_hash, sha256_file


class LlmUnavailable(Exception):
    """No usable model answer for this unit: the caller falls back to the rule-based proposer."""


class LedgerMiss(LlmUnavailable):
    """Replay was asked for a call that was never recorded. Never answered by a silent live call."""


class RecordedFailure(LlmUnavailable):
    """The recorded call failed validation or was refused; the failure is evidence too and replays as a failure."""


def call_key(model: str, settings: dict[str, Any], prompt_version: str, schema: type[BaseModel],
             packet: dict[str, Any]) -> str:
    """Anything that can change the answer is part of the key, so a changed prompt or model forces a new recording."""
    return json_hash({"model": model, "settings": settings, "prompt_version": prompt_version,
                      "schema": schema.model_json_schema(), "packet": packet})


class Ledger:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.entries: dict[str, dict[str, Any]] = {}
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    entry = json.loads(line)
                    self.entries[entry["key"]] = entry

    def get(self, key: str) -> dict[str, Any] | None:
        return self.entries.get(key)

    def append(self, entry: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(entry, sort_keys=True, ensure_ascii=False, default=str) + "\n")
        self.entries[entry["key"]] = entry

    def sha256(self) -> str | None:
        return sha256_file(self.path) if self.path.exists() else None
