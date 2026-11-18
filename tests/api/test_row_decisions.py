"""Pass and Override only where the table allows, a decision is bound to its evidence, and no figure moves on a pass."""
from typing import Any

from fastapi.testclient import TestClient

from tests.api.conftest import sample_run


def _decide(client: TestClient, run_id: str, name: str, key: str, action: str = "pass",
            reviewer: str = "reviewer") -> Any:
    body = {"key": key, "action": action, "reviewer": reviewer, "note": "looked"}
    return client.post(f"/api/runs/{run_id}/inputs/{name}/decisions", json=body)


def _finding(client: TestClient, run_id: str, name: str, code: str) -> dict[str, Any]:
    rows = client.get(f"/api/runs/{run_id}/inputs/{name}/rows").json()["rows"]
    return next(f for r in rows for f in r["findings"] if f["code"] == code)


def test_every_finding_starts_open_except_notes(client: TestClient) -> None:
    run_id = sample_run(client)
    files = {f["name"]: f for f in client.get(f"/api/runs/{run_id}/inputs").json()}
    assert files["adjustments.json"]["open"] == 6 and files["adjustments.json"]["status"] == "open"
    assert files["in_pl_monthly.csv"]["total"] == 2 and files["in_pl_monthly.csv"]["open"] == 0
    assert files["in_pl_monthly.csv"]["status"] == "noted"
    assert files["fx_rates.csv"]["status"] == "clean" and files["tb_uk.csv"]["total"] == 1


def test_a_pass_is_recorded_with_the_name_and_marks_the_row_reviewed(client: TestClient) -> None:
    run_id = sample_run(client)
    finding = _finding(client, run_id, "tb_uk.csv", "D08")
    assert _decide(client, run_id, "tb_uk.csv", finding["key"], reviewer="A. Reviewer").status_code == 200
    body = client.get(f"/api/runs/{run_id}/inputs/tb_uk.csv/rows").json()
    row = next(r for r in body["rows"] if r["line"] == 3)
    assert row["review"] == "reviewed" and row["findings"][0]["state"] == "passed"
    assert row["findings"][0]["decision"]["reviewer"] == "A. Reviewer"
    assert body["review"] == {"open": 0, "total": 1, "status": "reviewed"}


def test_a_decision_needs_a_name(client: TestClient) -> None:
    run_id = sample_run(client)
    key = _finding(client, run_id, "tb_uk.csv", "D08")["key"]
    assert _decide(client, run_id, "tb_uk.csv", key, reviewer="  ").status_code == 422
    assert client.get(f"/api/runs/{run_id}/inputs").json()[13]["open"] == 1


def test_hard_rules_cannot_be_overridden_and_say_so(client: TestClient) -> None:
    run_id = sample_run(client)
    for code in ("D03", "D04", "D05"):
        key = _finding(client, run_id, "adjustments.json", code)["key"]
        res = _decide(client, run_id, "adjustments.json", key, "override")
        assert res.status_code == 422 and "cannot be overridden" in res.json()["detail"]


def test_a_rule_with_no_engine_mechanism_is_acknowledge_only(client: TestClient) -> None:
    run_id = sample_run(client)
    key = _finding(client, run_id, "tb_uk.csv", "D08")["key"]
    res = _decide(client, run_id, "tb_uk.csv", key, "override")
    assert res.status_code == 422 and "No figure override" in res.json()["detail"]


def test_the_explain_endpoint_lists_which_actions_the_table_allows(client: TestClient) -> None:
    run_id = sample_run(client)
    body = client.get(f"/api/runs/{run_id}/inputs/adjustments.json/rows/102/explain").json()
    d03 = next(f for f in body["findings"] if f["code"] == "D03")
    assert d03["actions"]["pass"] is True and d03["actions"]["override"] is False
    assert "cannot be overridden" in d03["actions"]["override_note"]


def test_passing_a_held_journal_closes_its_waiting_item_and_moves_no_figure(client: TestClient) -> None:
    run_id = sample_run(client)
    meta = client.post(f"/api/runs/{run_id}/analyse").json()
    assert sorted(meta["open_items"]) == ["journal:JE-009", "journal:JE-016"]
    before = client.get(f"/api/runs/{run_id}/review").json()["dispositions"]
    for code in ("D06", "D07"):
        key = _finding(client, run_id, "adjustments.json", code)["key"]
        assert _decide(client, run_id, "adjustments.json", key).status_code == 200
    run = client.get(f"/api/runs/{run_id}").json()
    assert run["status"] == "done" and run["open_items"] == []
    assert client.get(f"/api/runs/{run_id}/review").json()["dispositions"] == before


def test_an_unknown_finding_key_is_404(client: TestClient) -> None:
    run_id = sample_run(client)
    assert _decide(client, run_id, "tb_uk.csv", "D08:tb_uk.csv:99:").status_code == 404


def test_a_decision_goes_stale_when_the_row_changes(client: TestClient) -> None:
    run_id = sample_run(client)
    key = _finding(client, run_id, "tb_uk.csv", "D08")["key"]
    _decide(client, run_id, "tb_uk.csv", key)
    path = client.app.state.registry.data_dir(run_id) / "tb_uk.csv"  # type: ignore[attr-defined]
    text = path.read_text(encoding="utf-8").replace("40000.00", "41000.00")
    path.write_text(text, encoding="utf-8", newline="")
    row = next(r for r in client.get(f"/api/runs/{run_id}/inputs/tb_uk.csv/rows").json()["rows"] if r["line"] == 3)
    assert row["findings"][0]["state"] == "stale" and row["review"] == "stale"


def test_the_mapping_override_is_offered_only_while_it_waits_and_signs_it_off(client: TestClient) -> None:
    run_id = sample_run(client)
    config = client.app.state.registry.config_dir(run_id) / "overrides.toml"  # type: ignore[attr-defined]
    config.write_text(config.read_text(encoding="utf-8").replace('status = "approved"', 'status = "open"'),
                      encoding="utf-8", newline="")
    assert "mapping:UK:2310" in client.post(f"/api/runs/{run_id}/analyse").json()["open_items"]
    key = _finding(client, run_id, "map_uk.csv", "D02")["key"]
    explained = client.get(f"/api/runs/{run_id}/inputs/map_uk.csv/rows/12/explain").json()
    assert explained["findings"][0]["actions"]["override"] is True
    assert _decide(client, run_id, "map_uk.csv", key, "override", "J. Reviewer").status_code == 200
    assert "mapping:UK:2310" not in client.get(f"/api/runs/{run_id}").json()["open_items"]
    assert 'approver = "J. Reviewer"' in config.read_text(encoding="utf-8")
    again = client.get(f"/api/runs/{run_id}/inputs/map_uk.csv/rows/12/explain").json()
    assert again["findings"][0]["actions"]["override"] is False
