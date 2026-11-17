"""Create and read runs."""
import json
import sqlite3
from typing import Any


def create_run(conn: sqlite3.Connection, run_id: str, input_hash: str, manifest: dict[str, Any]) -> None:
    """A run id is the hash of its inputs, so repeating a run replaces its row rather than adding one."""
    with conn:
        conn.execute("DELETE FROM runs WHERE run_id = ?", (run_id,))
        conn.execute(
            "INSERT INTO runs (run_id, input_hash, manifest) VALUES (?, ?, ?)",
            (run_id, input_hash, json.dumps(manifest)),
        )


def get_manifest(conn: sqlite3.Connection, run_id: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT manifest FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    return None if row is None else dict(json.loads(row["manifest"]))


def latest_run_id(conn: sqlite3.Connection) -> str | None:
    row = conn.execute("SELECT run_id FROM runs ORDER BY seq DESC LIMIT 1").fetchone()
    return None if row is None else str(row["run_id"])
