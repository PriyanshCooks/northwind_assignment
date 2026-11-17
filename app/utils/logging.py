"""JSON-lines run logger with run_id, stage and event fields. Standard library only.

Timestamps live here and nowhere else, so the required outputs stay byte-identical between runs."""
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        stamp = datetime.fromtimestamp(record.created, UTC).isoformat()
        body: dict[str, Any] = {"ts": stamp, **record.__dict__["fields"]}
        return json.dumps(body, ensure_ascii=False, default=str)


class RunLogger:
    """One log file per execution: <run_id>_<utc time>.jsonl. Closing it releases the file."""

    def __init__(self, folder: Path, run_id: str) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
        self.path = folder / f"{run_id}_{stamp}.jsonl"
        self.run_id = run_id
        self._logger = logging.getLogger(f"northwind.{run_id}.{stamp}")
        self._logger.setLevel(logging.INFO)
        self._logger.propagate = False
        self._handler = logging.FileHandler(self.path, encoding="utf-8")
        self._handler.setFormatter(_JsonFormatter())
        self._logger.addHandler(self._handler)

    def event(self, stage: str, event: str, **fields: object) -> None:
        self._logger.info(event, extra={"fields": {"run_id": self.run_id, "stage": stage, "event": event, **fields}})

    def close(self) -> None:
        self._logger.removeHandler(self._handler)
        self._handler.close()
