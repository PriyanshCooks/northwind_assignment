"""The ledger: every model call, one JSON line each, in ledger/<model>.jsonl. A run replays from it, so a fresh clone
gives the same answers offline. The local model is not repeatable, so this file is the only source of determinism."""
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from app.utils.env import scrub
from app.utils.hashing import json_hash, sha256_file


class LlmUnavailable(Exception):
    """No usable model answer for this unit: the caller falls back to the rule-based proposer."""


class LlmStop(Exception):
    """The run must stop, not fall back: a rejected key, no credit, or no key at all. Retrying cannot help."""


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
        self.used: set[str] = set()  # keys this run answered from or added to the file
        self.new_keys: set[str] = set()
        self.failed_in_a_row = 0  # live calls only: the circuit breaker in client.py reads it
        if path.exists():
            lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
            for number, line in enumerate(lines):
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    if number == len(lines) - 1:
                        continue  # a write cut off by a crash: that call is simply asked again
                    raise
                self.entries[entry["key"]] = entry

    def get(self, key: str) -> dict[str, Any] | None:
        entry = self.entries.get(key)
        if entry is not None:
            self.used.add(key)
        return entry

    def append(self, entry: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            line = scrub(json.dumps(entry, sort_keys=True, ensure_ascii=False, default=str))
            handle.write(line + "\n")
        self.entries[entry["key"]] = json.loads(line)
        self.used.add(entry["key"])
        self.new_keys.add(entry["key"])

    def sha256(self) -> str | None:
        return sha256_file(self.path) if self.path.exists() else None
