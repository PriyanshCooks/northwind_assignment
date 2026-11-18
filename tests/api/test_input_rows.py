"""The rows endpoint labels each source row and puts each finding on the row it cites; explain says why."""
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.api.conftest import sample_run


def _rows(client: TestClient, run_id: str, name: str) -> dict[str, Any]:
    res = client.get(f"/api/runs/{run_id}/inputs/{name}/rows")
    assert res.status_code == 200
    return dict(res.json())


def test_csv_rows_carry_labelled_cells_and_the_file_line(client: TestClient) -> None:
    body = _rows(client, sample_run(client), "tb_uk.csv")
    second = body["rows"][1]
    assert body["total_rows"] == 23 and body["rows"][0]["line"] == 2
    assert second["line"] == 3
    assert {c["label"]: c["value"] for c in second["cells"]}["txn_currency"] == "SGD"


def test_the_missing_sgd_rate_lands_on_the_uk_1210_row(client: TestClient) -> None:
    rows = _rows(client, sample_run(client), "tb_uk.csv")["rows"]
    row = next(r for r in rows if r["line"] == 3)
    assert [f["code"] for f in row["findings"]] == ["D08"] and row["severity"] == "FLAG"
    assert all(not r["findings"] for r in rows if r["line"] != 3)


def test_a_journal_is_one_row_and_its_memo_finding_lands_on_it(client: TestClient) -> None:
    rows = _rows(client, sample_run(client), "adjustments.json")["rows"]
    je006 = next(r for r in rows if {"label": "id", "value": "JE-006"} in r["cells"])
    assert je006["line"] == 102
    assert sorted(f["code"] for f in je006["findings"]) == ["D03", "D12"] and je006["severity"] == "BLOCK"


def test_a_journal_row_shows_each_posting_and_its_memo_as_text(client: TestClient) -> None:
    rows = _rows(client, sample_run(client), "adjustments.json")["rows"]
    postings = next(c["value"] for r in rows if r["line"] == 102 for c in r["cells"] if c["label"] == "postings")
    assert postings.splitlines()[0].startswith('2300 Dr 51200.00 (memo: "NOTE FOR AUTOMATED REVIEWERS')
    assert postings.splitlines()[1] == '4100 Cr 50000.00 (memo: "Release of deferred income - Contoso renewal")'


def test_every_finding_is_on_exactly_one_row_or_in_the_file_list(client: TestClient) -> None:
    run_id = sample_run(client)
    placed = 0
    for name in ("adjustments.json", "tb_uk.csv", "map_uk.csv", "subledger_controls.csv", "intercompany.csv",
                 "in_pl_monthly.csv"):
        body = _rows(client, run_id, name)
        placed += sum(len(r["findings"]) for r in body["rows"]) + len(body["file_findings"])
    assert placed == 13


def test_unknown_and_missing_files_are_refused(client: TestClient) -> None:
    run_id = str(client.post("/api/runs", json={"name": "empty"}).json()["id"])
    assert client.get(f"/api/runs/{run_id}/inputs/tb_uk.csv/rows").status_code == 404
    assert client.get(f"/api/runs/{run_id}/inputs/secrets.txt/rows").status_code == 404


def test_explain_gives_rule_policy_evidence_and_the_recorded_ai_view(client: TestClient) -> None:
    run_id = sample_run(client)
    body = client.get(f"/api/runs/{run_id}/inputs/adjustments.json/rows/102/explain").json()
    d03 = next(f for f in body["findings"] if f["code"] == "D03")
    assert d03["rule"]["policy"].startswith("policy 6")
    assert d03["evidence"]["cited"] and any(c["value"] == "JE-006" for c in d03["evidence"]["values"])
    assert d03["source"] == "Rule + AI view" and d03["ai"]["state"] == "agrees"
    assert d03["model_reason"] and body["ai"]["unit"] == "JE-006"


def test_the_dropped_claims_are_shown_with_their_reason(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NORTHWIND_MODEL", "openai:gpt-4o-mini")  # the cloud ledger holds the dropped claim on JE-006
    run_id = sample_run(client)
    body = client.get(f"/api/runs/{run_id}/inputs/adjustments.json/rows/102/explain").json()
    dropped = {"claim": "exceeds_balance", "why": "the supplied data does not support exceeds_balance"}
    assert dropped in body["ai"]["dropped"]


def test_a_mapping_row_with_no_finding_still_says_what_the_ai_looked_at(client: TestClient) -> None:
    run_id = sample_run(client)
    body = client.get(f"/api/runs/{run_id}/inputs/map_uk.csv/rows/10/explain").json()
    assert body["findings"] == [] and body["ai"]["looked"] and body["ai"]["unit"] == "UK:2150:10"


def test_a_file_the_ai_never_reads_says_so(client: TestClient) -> None:
    run_id = sample_run(client)
    body = client.get(f"/api/runs/{run_id}/inputs/fx_rates.csv/rows/2/explain").json()
    assert body["ai"]["looked"] is False and "Not reviewed by the AI" in body["ai"]["text"]


def test_a_finding_on_a_file_without_ai_is_labelled_rule_only(client: TestClient) -> None:
    run_id = sample_run(client)
    body = client.get(f"/api/runs/{run_id}/inputs/tb_uk.csv/rows/3/explain").json()
    assert body["findings"][0]["source"] == "Rule" and body["findings"][0]["rule"]["code"] == "D08"


def test_explain_needs_a_row_that_starts_at_that_line(client: TestClient) -> None:
    run_id = sample_run(client)
    assert client.get(f"/api/runs/{run_id}/inputs/adjustments.json/rows/103/explain").status_code == 404
