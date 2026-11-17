"""Store findings."""
import sqlite3

from app.domain.findings import Finding


def upsert_findings(conn: sqlite3.Connection, run_id: str, findings: list[Finding]) -> None:
    with conn:
        for finding in findings:
            conn.execute(
                "INSERT OR REPLACE INTO findings (run_id, key, code, severity, body) VALUES (?, ?, ?, ?, ?)",
                (run_id, finding.key, finding.code, finding.severity, finding.model_dump_json()),
            )
