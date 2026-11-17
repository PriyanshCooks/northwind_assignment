"""Store and fetch recorded AI calls, keyed by the hash of what was asked."""
import json
import sqlite3
from typing import Any


def put_call(conn: sqlite3.Connection, key: str, model: str, body: dict[str, Any]) -> None:
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO llm_ledger (key, model, body) VALUES (?, ?, ?)",
            (key, model, json.dumps(body)),
        )


def get_call(conn: sqlite3.Connection, key: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT body FROM llm_ledger WHERE key = ?", (key,)).fetchone()
    return None if row is None else dict(json.loads(row["body"]))
