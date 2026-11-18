"""Choose outputs before generating, sign off the generated files, and the calculation behind an output row."""
import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from tests.api.conftest import finished_run, sample_run


def _zip_names_and_signoff(client: TestClient, run_id: str) -> tuple[list[str], dict[str, object]]:
    archive = zipfile.ZipFile(io.BytesIO(client.get(f"/api/runs/{run_id}/export").content))
    return sorted(archive.namelist()), json.loads(archive.read("signoff.json"))


def test_the_output_plan_is_known_before_anything_is_generated(client: TestClient) -> None:
    run_id = sample_run(client)
    assert client.get(f"/api/runs/{run_id}/output-plan").status_code == 409  # nothing scanned yet
    client.post(f"/api/runs/{run_id}/analyse")
    plan = client.get(f"/api/runs/{run_id}/output-plan").json()
    assert len(plan["available"]) == 9
    assert client.put(f"/api/runs/{run_id}/output-plan", json={"files": ["issues.json"]}).status_code == 200
    chosen = client.get(f"/api/runs/{run_id}/output-plan").json()["chosen"]
    assert chosen == ["issues.json", "run_manifest.json"]  # the manifest is always kept


def test_a_plan_outside_the_nine_files_is_refused(client: TestClient) -> None:
    run_id = sample_run(client)
    client.post(f"/api/runs/{run_id}/analyse")
    assert client.put(f"/api/runs/{run_id}/output-plan", json={"files": ["../run.json"]}).status_code == 422


def test_reviewing_the_files_clears_only_the_file_reason_for_a_draft(client: TestClient) -> None:
    run_id = finished_run(client)
    client.put(f"/api/runs/{run_id}/output-plan", json={"files": ["balance_sheet.json"]})
    before = client.get(f"/api/runs/{run_id}/signoff").json()
    assert before["status"] == "Draft" and all(f["state"] == "open" for f in before["files"])
    for f in before["files"]:
        client.post(f"/api/runs/{run_id}/signoff", json={"file": f["name"], "reviewer": "Dana"})
    after = client.get(f"/api/runs/{run_id}/signoff").json()
    assert {f["reviewed_by"] for f in after["files"]} == {"Dana"}
    # the files are reviewed, but the sample still has input findings nobody passed, so it stays a Draft and says why
    assert after["status"] == "Draft" and all("input" in r for r in after["reasons"])


def test_the_status_is_written_into_the_zip_and_the_manifest_is_untouched(client: TestClient) -> None:
    run_id = finished_run(client)
    client.put(f"/api/runs/{run_id}/outputs", json={"files": ["balance_sheet.json"]})
    names, signoff = _zip_names_and_signoff(client, run_id)
    assert names == ["balance_sheet.json", "run_manifest.json", "signoff.json"]
    assert signoff["status"] == "Draft" and signoff["reasons"]


def test_marking_reviewed_needs_a_name_and_a_file_of_the_run(client: TestClient) -> None:
    run_id = finished_run(client)
    assert client.post(f"/api/runs/{run_id}/signoff", json={"file": "issues.json", "reviewer": " "}).status_code == 422
    assert client.post(f"/api/runs/{run_id}/signoff", json={"file": "../x", "reviewer": "Dana"}).status_code == 422


def test_a_calculation_is_read_from_the_recorded_run_and_an_unknown_target_is_a_404(client: TestClient) -> None:
    run_id = finished_run(client)
    figure = client.get(f"/api/runs/{run_id}/calculation/goodwill_closing")
    assert figure.status_code == 200 and figure.json()["kind"] == "figure" and figure.json()["steps"]
    assert client.get(f"/api/runs/{run_id}/calculation/nothing-here").status_code == 404
    assert client.get(f"/api/runs/{run_id}/calculation/a b").status_code in {404, 422}


def test_final_when_nothing_is_open_and_every_file_is_reviewed(
        client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import generate_service

    run_id = finished_run(client)
    monkeypatch.setattr(generate_service, "unanswered", lambda registry, run: {"problems": 0, "draft": False})
    client.put(f"/api/runs/{run_id}/output-plan", json={"files": ["issues.json"]})
    for f in client.get(f"/api/runs/{run_id}/signoff").json()["files"]:
        client.post(f"/api/runs/{run_id}/signoff", json={"file": f["name"], "reviewer": "Dana"})
    done = client.get(f"/api/runs/{run_id}/signoff").json()
    assert done["status"] == "Final" and done["reasons"] == []
    _, signoff = _zip_names_and_signoff(client, run_id)
    assert signoff["status"] == "Final"


def test_a_row_mark_is_kept_per_file_hash_and_does_not_review_the_file(client: TestClient) -> None:
    run_id = finished_run(client)
    body = {"file": "balance_sheet.json", "reviewer": "Dana", "row": "1:0"}
    done = client.post(f"/api/runs/{run_id}/signoff", json=body).json()
    one = next(f for f in done["files"] if f["name"] == "balance_sheet.json")
    assert one["rows_reviewed"] == ["1:0"] and one["state"] == "open"
    bad = {"file": "balance_sheet.json", "reviewer": "Dana", "row": "../x"}
    assert client.post(f"/api/runs/{run_id}/signoff", json=bad).status_code == 422


def test_a_real_final_needs_every_finding_passed_and_every_file_reviewed(client: TestClient) -> None:
    run_id = finished_run(client)
    left = client.get(f"/api/runs/{run_id}/unanswered").json()
    for item in left["findings"]:
        body = {"key": item["key"], "action": "pass", "reviewer": "Dana", "note": "looked"}
        assert client.post(f"/api/runs/{run_id}/inputs/{item['file']}/decisions", json=body).status_code == 200
    for f in client.get(f"/api/runs/{run_id}/signoff").json()["files"]:
        client.post(f"/api/runs/{run_id}/signoff", json={"file": f["name"], "reviewer": "Dana"})
    done = client.get(f"/api/runs/{run_id}/signoff").json()
    assert done["status"] == "Final" and done["reasons"] == [] and done["problems"] == 0
    _, signoff = _zip_names_and_signoff(client, run_id)
    assert signoff["status"] == "Final"
