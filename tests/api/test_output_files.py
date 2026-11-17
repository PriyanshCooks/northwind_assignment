"""The output viewer's routes: a list with metadata, one file as tables, the issues that touch it, and a download."""
import hashlib

from fastapi.testclient import TestClient

from tests.api.conftest import finished_run


def test_the_list_has_one_entry_per_output_file_with_rows_and_hash(client: TestClient) -> None:
    run_id = finished_run(client)
    rows = client.get(f"/api/runs/{run_id}/output-files").json()
    names = [r["name"] for r in rows]
    assert names == [o["name"] for o in client.get(f"/api/runs/{run_id}/outputs").json()["available"]]
    tb = next(r for r in rows if r["name"] == "consolidated_tb.csv")
    body = client.get(f"/api/runs/{run_id}/output-files/consolidated_tb.csv/download").content
    assert tb["sha256"] == hashlib.sha256(body).hexdigest() and tb["rows"] == body.decode().count("\n") - 1


def test_a_csv_opens_as_a_table_and_money_keeps_its_exact_text(client: TestClient) -> None:
    run_id = finished_run(client)
    view = client.get(f"/api/runs/{run_id}/output-files/consolidated_tb.csv").json()
    assert view["sections"][0]["columns"][:2] == ["group_code", "group_name"] and not view["truncated"]
    figures = client.get(f"/api/runs/{run_id}/output-files/control_figures_pb.json").json()
    rows = dict(figures["sections"][0]["rows"])
    assert rows["group_revenue"] == "28301607.81" and rows["sgd_bank_gbp"] == ""


def test_a_statement_opens_as_sections_of_accounts(client: TestClient) -> None:
    run_id = finished_run(client)
    sheet = client.get(f"/api/runs/{run_id}/output-files/balance_sheet.json").json()
    assert any("account" in s["columns"] for s in sheet["sections"])


def test_an_unknown_file_and_a_path_trick_are_refused(client: TestClient) -> None:
    run_id = finished_run(client)
    assert client.get(f"/api/runs/{run_id}/output-files/secret.txt").status_code == 422
    assert client.get(f"/api/runs/{run_id}/output-files/..%2Frun.json/download").status_code in {404, 422}


def test_issues_trace_to_a_file_by_source_rows_and_the_rest_are_run_wide(client: TestClient) -> None:
    run_id = finished_run(client)
    got = client.get(f"/api/runs/{run_id}/output-files/consolidated_tb.csv/issues").json()
    traced = {c["headline"][:20] for c in got["affecting"]}
    assert any(h.startswith("UK 1210 holds SGD") for h in traced)
    assert any(c["code"] == "D12" for c in got["run_wide"])
    every = client.get(f"/api/runs/{run_id}/output-files/issues.json/issues").json()
    total = len(client.get(f"/api/runs/{run_id}/results").json()["cards"])
    assert every["run_wide"] == [] and len(every["affecting"]) == total


def test_files_are_not_served_before_the_run_finishes(client: TestClient) -> None:
    from tests.api.conftest import sample_run
    run_id = sample_run(client)
    assert client.get(f"/api/runs/{run_id}/output-files").status_code == 409
