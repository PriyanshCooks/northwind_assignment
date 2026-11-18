"""Generate output is always available once scanned; with items unanswered it is a Draft and they stay problems."""
from typing import Any

from fastapi.testclient import TestClient

from tests.api.conftest import finished_run, sample_run


def _generate(client: TestClient, run_id: str) -> Any:
    return client.post(f"/api/runs/{run_id}/generate")


def test_a_run_that_was_never_scanned_says_to_scan_first(client: TestClient) -> None:
    res = _generate(client, sample_run(client))
    assert res.status_code == 409 and "scan the files first" in res.json()["detail"]


def test_with_items_waiting_the_output_is_a_draft_and_every_item_is_still_listed(client: TestClient) -> None:
    run_id = sample_run(client)
    client.post(f"/api/runs/{run_id}/analyse")
    body = _generate(client, run_id).json()
    assert body["draft"] is True and body["passed"] is True and len(body["gates"]) == 20
    assert sorted(body["unanswered"]["engine_items"]) == ["journal:JE-009", "journal:JE-016"]
    assert len(body["unanswered"]["findings"]) == 11  # 13 findings less the 2 notes, which need no decision
    assert body["unanswered"]["problems"] == 11  # the two held journals are the D06 and D07 findings, counted once
    assert client.get(f"/api/runs/{run_id}").json()["status"] == "awaiting_review"


def test_the_draft_is_readable_and_equals_the_final_figures(client: TestClient) -> None:
    run_id = sample_run(client)
    client.post(f"/api/runs/{run_id}/analyse")
    _generate(client, run_id)
    draft = {f["key"]: f["value"] for f in client.get(f"/api/runs/{run_id}/results").json()["figures"]}
    final = {f["key"]: f["value"] for f in client.get(f"/api/runs/{finished_run(client)}/results").json()["figures"]}
    assert draft == final  # held journals stay out either way; nothing undecided moved a figure


def test_results_stay_refused_until_a_draft_is_generated(client: TestClient) -> None:
    run_id = sample_run(client)
    client.post(f"/api/runs/{run_id}/analyse")
    assert client.get(f"/api/runs/{run_id}/results").status_code == 409
    _generate(client, run_id)
    assert client.get(f"/api/runs/{run_id}/results").status_code == 200


def test_a_draft_goes_stale_when_an_input_changes(client: TestClient) -> None:
    run_id = sample_run(client)
    client.post(f"/api/runs/{run_id}/analyse")
    _generate(client, run_id)
    path = client.app.state.registry.data_dir(run_id) / "tb_uk.csv"  # type: ignore[attr-defined]
    path.write_text(path.read_text(encoding="utf-8").replace("40000.00", "41000.00"), encoding="utf-8", newline="")
    assert client.get(f"/api/runs/{run_id}/results").status_code == 409


def test_passing_a_finding_does_not_close_it_for_the_engine_but_clears_it_from_the_problems(client: TestClient) -> None:
    run_id = sample_run(client)
    client.post(f"/api/runs/{run_id}/analyse")
    key = next(f["key"] for f in client.get(f"/api/runs/{run_id}/unanswered").json()["findings"] if f["code"] == "D08")
    client.post(f"/api/runs/{run_id}/inputs/tb_uk.csv/decisions", json={"key": key, "action": "pass", "reviewer": "a"})
    left = client.get(f"/api/runs/{run_id}/unanswered").json()
    assert key not in [f.get("key") for f in left["findings"]] and len(left["findings"]) == 10
    assert left["draft"] is True


def test_findings_nobody_passed_keep_the_output_a_draft_even_when_the_engine_is_done(client: TestClient) -> None:
    run_id = finished_run(client)
    body = _generate(client, run_id).json()
    assert body["passed"] is True and body["draft"] is True and len(body["unanswered"]["findings"]) == 11
    assert body["unanswered"]["engine_items"] == []


def test_with_every_finding_passed_the_output_is_not_a_draft(client: TestClient) -> None:
    run_id = sample_run(client)
    client.post(f"/api/runs/{run_id}/analyse")
    for f in client.get(f"/api/runs/{run_id}/unanswered").json()["findings"]:
        body = {"key": f["key"], "action": "pass", "reviewer": "a"}
        assert client.post(f"/api/runs/{run_id}/inputs/{f['file']}/decisions", json=body).status_code == 200
    body = _generate(client, run_id).json()
    left = {"engine_items": [], "findings": [], "problems": 0, "draft": False}
    assert body["draft"] is False and body["unanswered"] == left
