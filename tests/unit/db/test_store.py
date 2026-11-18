import sqlite3
from decimal import Decimal

import pytest

from app.db.connection import connect
from app.db.findings_service import upsert_findings
from app.db.lineage_service import get_trace, origin_rows, store_origin_rows, store_trace
from app.db.runs_service import create_run, latest_run_id
from app.domain.entries import Posting, TraceStep
from app.domain.findings import Finding
from app.domain.refs import make_ref

REF = make_ref("tb_uk.csv", 11, "row")


def finding(key: str = "D09:subledger_controls.csv:4:control_total") -> Finding:
    return Finding(
        key=key, code="D09", severity="FLAG", claim="UK receivables differ from the sub-ledger",
        file="subledger_controls.csv", line=4, amount_affected="45000.00", action="flagged",
    )


def test_finding_is_upserted_by_key() -> None:
    conn = connect(":memory:")
    upsert_findings(conn, "r1", [finding()])
    upsert_findings(conn, "r1", [finding()])
    assert conn.execute("SELECT COUNT(*) FROM findings").fetchone()[0] == 1


def test_repeating_a_run_replaces_it() -> None:
    conn = connect(":memory:")
    create_run(conn, "r1", "abc", {"n": 1})
    create_run(conn, "r1", "abc", {"n": 2})
    assert conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 1
    assert latest_run_id(conn) == "r1"


def test_malformed_json_cannot_be_stored() -> None:
    conn = connect(":memory:")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO findings (run_id, key, code, severity, body) VALUES ('r', 'k', 'D01', 'NOTE', 'not json')")


def test_origin_rows_come_back_in_order_with_exact_amounts() -> None:
    conn = connect(":memory:")
    amount = str(Decimal("10160.00") / Decimal("1.2530"))
    rows = [
        Posting(entity="UK", account="6300", amount=amount, ccy="GBP", origin="ELIMINATION", sources=(REF,)),
        Posting(entity="UK", account="6300", amount="490707.72", ccy="GBP", origin="IMPORT", sources=(REF,)),
    ]
    store_origin_rows(conn, "r1", rows)
    assert origin_rows(conn, "r1", "6300") == rows
    assert origin_rows(conn, "r1", "9999") == []


def test_trace_is_stored_and_read_back() -> None:
    conn = connect(":memory:")
    step = TraceStep(
        figure="goodwill_closing", formula="INR 147,600,000 / 107.28186",
        inputs=("acquisition_note.md:5",), result="1375815.07",
    )
    steps = [step]
    store_trace(conn, "r1", "goodwill_closing", steps)
    assert get_trace(conn, "r1", "goodwill_closing") == steps
    assert get_trace(conn, "r1", "other") is None
