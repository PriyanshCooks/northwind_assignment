import sqlite3
from decimal import Decimal

import pytest

from app.db.connection import connect
from app.db.facts_service import get_fact, is_stale, put_fact
from app.db.findings_service import list_findings, upsert_findings
from app.db.ledger_service import get_call, put_call
from app.db.lineage_service import get_trace, origin_rows, store_origin_rows, store_trace
from app.db.runs_service import create_run, get_manifest, latest_run_id
from app.domain.entries import Posting, TraceStep
from app.domain.findings import Finding
from app.domain.refs import make_ref

REF = make_ref("tb_uk.csv", 11, "row")


def finding(key: str = "D09:subledger_controls.csv:4:control_total") -> Finding:
    return Finding(
        key=key, code="D09", severity="FLAG", claim="UK receivables differ from the sub-ledger",
        file="subledger_controls.csv", line=4, amount_affected="45000.00", action="flagged",
    )


def test_malformed_json_cannot_be_stored() -> None:
    conn = connect(":memory:")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO llm_ledger (key, model, body) VALUES ('k', 'm', 'not json')")


def test_run_is_stored_and_read_back() -> None:
    conn = connect(":memory:")
    create_run(conn, "r1", "abc", {"policy_sha256": "00888e75"})
    assert get_manifest(conn, "r1") == {"policy_sha256": "00888e75"}
    assert latest_run_id(conn) == "r1"


def test_repeating_a_run_replaces_it() -> None:
    conn = connect(":memory:")
    create_run(conn, "r1", "abc", {"n": 1})
    create_run(conn, "r1", "abc", {"n": 2})
    assert get_manifest(conn, "r1") == {"n": 2}


def test_finding_is_upserted_by_key() -> None:
    conn = connect(":memory:")
    upsert_findings(conn, "r1", [finding()])
    upsert_findings(conn, "r1", [finding()])
    assert len(list_findings(conn, "r1")) == 1


def test_finding_amount_keeps_its_decimal_exactly() -> None:
    conn = connect(":memory:")
    upsert_findings(conn, "r1", [finding()])
    assert list_findings(conn, "r1")[0].amount_affected == Decimal("45000.00")


def test_recorded_ai_call_is_fetched_by_key() -> None:
    conn = connect(":memory:")
    put_call(conn, "abc123", "qwen3:4b", {"risk": False})
    assert get_call(conn, "abc123") == {"risk": False}
    assert get_call(conn, "missing") is None


def test_decision_goes_stale_when_its_evidence_changes() -> None:
    conn = connect(":memory:")
    put_fact(conn, "mapping:UK:2310", "hash-v1", {"decision": "remap", "to": "2300"})
    assert get_fact(conn, "mapping:UK:2310") == {"decision": "remap", "to": "2300"}
    assert not is_stale(conn, "mapping:UK:2310", "hash-v1")
    assert is_stale(conn, "mapping:UK:2310", "hash-v2")


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
