"""Scan progress is what the run log recorded, file by file."""
from fastapi.testclient import TestClient

from tests.api.conftest import sample_run


def test_before_the_scan_every_present_file_is_waiting(client: TestClient) -> None:
    body = client.get(f"/api/runs/{sample_run(client)}/scan").json()
    assert body["finished"] is False and body["scanned"] == 0 and body["total"] == 15
    assert {f["status"] for f in body["files"]} == {"waiting"}


def test_after_the_scan_each_file_shows_its_finding_count_from_the_log(client: TestClient) -> None:
    run_id = sample_run(client)
    client.post(f"/api/runs/{run_id}/analyse")
    body = client.get(f"/api/runs/{run_id}/scan").json()
    counts = {f["name"]: f["findings"] for f in body["files"]}
    assert body["finished"] is True and body["scanned"] == 15
    assert counts["adjustments.json"] == 6 and counts["tb_uk.csv"] == 1 and counts["fx_rates.csv"] == 0


def test_a_file_that_was_never_uploaded_is_missing_not_waiting(client: TestClient) -> None:
    run_id = str(client.post("/api/runs", json={"name": "empty"}).json()["id"])
    body = client.get(f"/api/runs/{run_id}/scan").json()
    assert {f["status"] for f in body["files"]} == {"missing"} and body["total"] == 0


def test_a_second_scan_reads_the_newest_log_only(client: TestClient) -> None:
    run_id = sample_run(client)
    client.post(f"/api/runs/{run_id}/analyse")
    client.post(f"/api/runs/{run_id}/analyse")
    assert client.get(f"/api/runs/{run_id}/scan").json()["scanned"] == 15
