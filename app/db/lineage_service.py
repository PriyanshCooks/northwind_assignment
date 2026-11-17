"""Store origin rows and traces, and answer `trace`."""
import json
import sqlite3

from app.domain.entries import Posting, TraceStep

INSERT_ROW = "INSERT INTO origin_rows (run_id, account, seq, body) VALUES (?, ?, ?, ?)"
SELECT_ROWS = "SELECT body FROM origin_rows WHERE run_id = ? AND account = ? ORDER BY seq"


def store_origin_rows(conn: sqlite3.Connection, run_id: str, rows: list[Posting]) -> None:
    with conn:
        conn.execute("DELETE FROM origin_rows WHERE run_id = ?", (run_id,))
        for seq, row in enumerate(rows):
            conn.execute(INSERT_ROW, (run_id, row.account, seq, row.model_dump_json()))


def origin_rows(conn: sqlite3.Connection, run_id: str, account: str) -> list[Posting]:
    found = conn.execute(SELECT_ROWS, (run_id, account)).fetchall()
    return [Posting.model_validate_json(row["body"]) for row in found]


def store_trace(conn: sqlite3.Connection, run_id: str, figure: str, steps: list[TraceStep]) -> None:
    body = "[" + ",".join(step.model_dump_json() for step in steps) + "]"
    with conn:
        conn.execute("INSERT OR REPLACE INTO traces (run_id, figure, body) VALUES (?, ?, ?)", (run_id, figure, body))


def get_trace(conn: sqlite3.Connection, run_id: str, figure: str) -> list[TraceStep] | None:
    row = conn.execute("SELECT body FROM traces WHERE run_id = ? AND figure = ?", (run_id, figure)).fetchone()
    if row is None:
        return None
    return [TraceStep.model_validate(item) for item in json.loads(row["body"])]
