"""The review flow end to end, and the check that the API shows the same 12 figures as run.py consolidate."""
import io
import json
import re
import zipfile
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

from app.cli import main as cli_main
from app.utils.paths import CONFIG_DIR, ROOT
from tests.api.conftest import finished_run, sample_run, settle

HELD = ["journal:JE-009", "journal:JE-016"]
APPROVED = 'status = "approved"'
CLOSING_GBP_USD = "fx_rates.csv:6.rate=1.3000"


def _reopen_the_override(client: TestClient, run_id: str) -> None:
    path = client.app.state.registry.config_dir(run_id) / "overrides.toml"  # type: ignore[attr-defined]
    path.write_text(path.read_text(encoding="utf-8").replace(APPROVED, 'status = "open"'), encoding="utf-8")


def _cli_figures(tmp_path: Path) -> dict[str, object]:
    out = tmp_path / "cli_out"
    assert cli_main(["consolidate", "--output", str(out), "--db", str(tmp_path / "cli.db")]) == 0
    text = (out / "control_figures_pb.json").read_text(encoding="utf-8")
    return dict(json.loads(text, parse_float=lambda t: str(Decimal(t).quantize(Decimal("0.01")))))


def _api_figures(client: TestClient, run_id: str) -> dict[str, object]:
    return {f["key"]: f["value"] for f in client.get(f"/api/runs/{run_id}/results").json()["figures"]}


def test_api_figures_equal_run_py_consolidate(client: TestClient, tmp_path: Path) -> None:
    api = _api_figures(client, finished_run(client))
    assert len(api) == 12
    assert api == _cli_figures(tmp_path)


def test_figures_after_a_pause_and_an_approval_still_equal_the_cli(client: TestClient, tmp_path: Path) -> None:
    run_id = sample_run(client)
    _reopen_the_override(client, run_id)
    paused = client.post(f"/api/runs/{run_id}/analyse").json()
    assert paused["status"] == "awaiting_review" and paused["open_items"] == ["mapping:UK:2310", *HELD]
    queue = client.get(f"/api/runs/{run_id}/review").json()["queue"]
    assert any(q["kind"] == "override" and q["key"] == "mapping:UK:2310" for q in queue)
    body = {"approver": "tester", "decisions": {k: "approve" for k in paused["open_items"]}}
    assert client.post(f"/api/runs/{run_id}/decisions", json=body).json()["status"] == "done"
    assert _api_figures(client, run_id) == _cli_figures(tmp_path)


def test_a_decision_on_an_item_that_is_not_open_is_refused(client: TestClient) -> None:
    run_id = sample_run(client)
    _reopen_the_override(client, run_id)
    client.post(f"/api/runs/{run_id}/analyse")
    body = {"approver": "tester", "decisions": {"mapping:IN:9999": "approve"}}
    assert client.post(f"/api/runs/{run_id}/decisions", json=body).status_code == 409
    bad = {"approver": "tester", "decisions": {"mapping:UK:2310": "maybe"}}
    assert client.post(f"/api/runs/{run_id}/decisions", json=bad).status_code == 422


def test_rejecting_changes_the_run_not_the_repository_config(client: TestClient) -> None:
    run_id = sample_run(client)
    _reopen_the_override(client, run_id)
    client.post(f"/api/runs/{run_id}/analyse")
    body = {"approver": "tester", "decisions": {"mapping:UK:2310": "reject"}}
    assert client.post(f"/api/runs/{run_id}/decisions", json=body).json()["open_items"] == HELD
    assert APPROVED in (CONFIG_DIR / "overrides.toml").read_text(encoding="utf-8")


def test_review_shows_findings_dispositions_and_dropped_claims(client: TestClient) -> None:
    review = client.get(f"/api/runs/{finished_run(client)}/review").json()
    assert len(review["findings"]) == 13 and review["dispositions"]
    assert any(a["dropped"] for a in review["advice"])


def test_an_input_the_ledger_never_saw_reads_not_recorded(client: TestClient) -> None:
    run_id = sample_run(client)
    path = client.app.state.registry.data_dir(run_id) / "tb_uk.csv"  # type: ignore[attr-defined]
    path.write_bytes(path.read_bytes().replace(b"Accounts receivable", b"Trade debtors"))
    advice = client.get(f"/api/runs/{run_id}/review").json()["advice"]
    assert all(a["recorded"] is False for a in advice if a["source"] == "rules")


def test_build_returns_the_twenty_gates(client: TestClient) -> None:
    built = client.post(f"/api/runs/{finished_run(client)}/build").json()
    assert len(built["gates"]) == 20 and built["passed"] is True and built["blocked"] is None


def test_results_carry_status_and_the_reason_for_a_null(client: TestClient) -> None:
    results = client.get(f"/api/runs/{finished_run(client)}/results").json()
    figs = {f["key"]: f for f in results["figures"]}
    assert figs["sgd_bank_gbp"]["value"] is None and "no GBP/SGD closing rate" in figs["sgd_bank_gbp"]["reason"]
    assert figs["group_profit"]["status"] == "provisional" and results["issues"]


def test_export_zip_holds_the_chosen_files_and_the_manifest(client: TestClient) -> None:
    run_id = finished_run(client)
    chosen = ["balance_sheet.json", "issues.json"]
    assert client.put(f"/api/runs/{run_id}/outputs", json={"files": chosen}).status_code == 200
    names = zipfile.ZipFile(io.BytesIO(client.get(f"/api/runs/{run_id}/export").content)).namelist()
    assert sorted(names) == ["balance_sheet.json", "issues.json", "run_manifest.json"]


def test_choosing_a_file_outside_the_output_folder_is_refused(client: TestClient) -> None:
    run_id = finished_run(client)
    assert client.put(f"/api/runs/{run_id}/outputs", json={"files": ["../run.json"]}).status_code == 422


def test_what_if_builds_a_new_run_and_leaves_the_old_one(client: TestClient) -> None:
    run_id = finished_run(client)
    before = _api_figures(client, run_id)
    new = client.post(f"/api/runs/{run_id}/whatif", json={"name": "closing 1.30", "patches": [CLOSING_GBP_USD]}).json()
    new = settle(client, new)
    assert new["parent"] == run_id and new["status"] == "done" and new["id"] != run_id
    assert _api_figures(client, run_id) == before
    assert _api_figures(client, new["id"])["total_assets"] != before["total_assets"]
    assert len(client.get("/api/runs").json()) == 2


def test_what_if_refuses_a_file_that_is_not_one_of_the_fifteen(client: TestClient) -> None:
    run_id = finished_run(client)
    bad = {"patches": ["../../config/policy.toml:1.x=1"]}
    assert client.post(f"/api/runs/{run_id}/whatif", json=bad).status_code == 422


def test_compare_lists_the_changed_lines_and_the_moved_figures(client: TestClient) -> None:
    run_id = finished_run(client)
    new = settle(client, client.post(f"/api/runs/{run_id}/whatif", json={"patches": [CLOSING_GBP_USD]}).json())
    out = client.get(f"/api/runs/{new['id']}/compare/{run_id}").json()
    assert out["input_changes"] == ["fx_rates.csv: changed at line(s) 6"]
    assert any(f["key"] == "total_assets" for f in out["figures"])
    assert "fx_rates.csv:6" in out["impact"]


def test_a_waiting_override_gets_a_card_with_its_reason_and_both_effects(client: TestClient) -> None:
    run_id = sample_run(client)
    _reopen_the_override(client, run_id)
    client.post(f"/api/runs/{run_id}/analyse")
    cards = client.get(f"/api/runs/{run_id}/review").json()["waiting"]
    (card,) = [c for c in cards if c["key"] == "mapping:UK:2310"]
    assert card["key"] == "mapping:UK:2310" and card["state"] == "open"
    assert "named exactly 'Deferred income'" in card["reason"]
    assert "signed off" in card["approve_effect"] and "stays in revenue 4100" in card["reject_effect"]


def test_nothing_past_review_runs_while_an_item_is_undecided(client: TestClient) -> None:
    run_id = sample_run(client)
    _reopen_the_override(client, run_id)
    client.post(f"/api/runs/{run_id}/analyse")
    other = finished_run(client)
    calls = [client.post(f"/api/runs/{run_id}/build"), client.get(f"/api/runs/{run_id}/results"),
             client.get(f"/api/runs/{run_id}/outputs"), client.put(f"/api/runs/{run_id}/outputs", json={"files": []}),
             client.get(f"/api/runs/{run_id}/export"), client.get(f"/api/runs/{run_id}/output-files"),
             client.get(f"/api/runs/{run_id}/compare/{other}")]
    for response in calls:
        assert response.status_code == 409 and "mapping:UK:2310" in response.json()["detail"]


def test_a_blank_name_is_refused_and_changes_nothing(client: TestClient) -> None:
    run_id = sample_run(client)
    _reopen_the_override(client, run_id)
    client.post(f"/api/runs/{run_id}/analyse")
    body = {"approver": "", "decisions": {"mapping:UK:2310": "approve"}}
    assert client.post(f"/api/runs/{run_id}/decisions", json=body).status_code == 422
    assert client.get(f"/api/runs/{run_id}").json()["status"] == "awaiting_review"


def test_the_workbench_script_asks_for_a_name_and_keeps_next_disabled_until_done() -> None:
    script = (ROOT / "frontend" / "workbench.js").read_text(encoding="utf-8")
    assert "Enter your name before you decide" in script
    assert 'next.disabled = state.run.status !== "done"' in script


def test_every_money_value_on_the_api_is_a_two_decimal_string(client: TestClient) -> None:
    results = client.get(f"/api/runs/{finished_run(client)}/results").json()
    money = {f["key"]: f["value"] for f in results["figures"]}
    assert money["group_revenue"] == "28301607.81" and money["sgd_bank_gbp"] is None
    assert money["journals"] == {"posted": 15, "rejected": 3, "held": 2}
    amounts = [i["amount_affected"] for i in results["issues"] if i["amount_affected"] is not None]
    assert amounts and all(isinstance(a, str) and re.fullmatch(r"-?\d+\.\d{2}", a) for a in amounts)
    assert not any(isinstance(v, float) for v in _walk(results))


def _walk(node: object) -> list[object]:
    if isinstance(node, dict):
        return [x for v in node.values() for x in _walk(v)]
    if isinstance(node, list):
        return [x for v in node for x in _walk(v)]
    return [node]


def test_held_journals_wait_for_a_named_decision_and_move_no_figure(client: TestClient, tmp_path: Path) -> None:
    run_id = sample_run(client)
    paused = client.post(f"/api/runs/{run_id}/analyse").json()
    assert paused["status"] == "awaiting_review" and paused["open_items"] == HELD
    cards = {c["key"]: c for c in client.get(f"/api/runs/{run_id}/review").json()["waiting"]}
    assert set(cards) == set(HELD) and "stays out of the figures" in cards["journal:JE-016"]["approve_effect"]
    blocked = client.get(f"/api/runs/{run_id}/results")
    assert blocked.status_code == 409 and all(k in blocked.json()["detail"] for k in HELD)
    one = client.post(f"/api/runs/{run_id}/decisions", json={"approver": "tester", "decisions": {HELD[0]: "reject"}})
    assert one.json()["open_items"] == [HELD[1]]
    both = {"approver": "tester", "decisions": {HELD[1]: "approve"}}
    assert client.post(f"/api/runs/{run_id}/decisions", json=both).json()["status"] == "done"
    assert _api_figures(client, run_id) == _cli_figures(tmp_path)
