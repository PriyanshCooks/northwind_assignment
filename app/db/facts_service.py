"""Human decisions, stored against a hash of the evidence they were made on (principle P8)."""
import json
import sqlite3
from typing import Any


def put_fact(conn: sqlite3.Connection, key: str, evidence_sha256: str, body: dict[str, Any]) -> None:
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO facts (key, evidence_sha256, body) VALUES (?, ?, ?)",
            (key, evidence_sha256, json.dumps(body)),
        )


def get_fact(conn: sqlite3.Connection, key: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT body FROM facts WHERE key = ?", (key,)).fetchone()
    return None if row is None else dict(json.loads(row["body"]))


def is_stale(conn: sqlite3.Connection, key: str, current_evidence_sha256: str) -> bool:
    """A decision whose evidence has changed no longer applies and goes back to the review queue."""
    row = conn.execute("SELECT evidence_sha256 FROM facts WHERE key = ?", (key,)).fetchone()
    return row is not None and str(row["evidence_sha256"]) != current_evidence_sha256
