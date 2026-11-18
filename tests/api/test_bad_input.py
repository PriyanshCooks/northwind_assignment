from fastapi.testclient import TestClient

from app.utils.paths import DEFAULT_DATA_DIR
from tests.api.conftest import finished_run, sample_run


def test_a_month_outside_the_year_gives_422_with_the_place_and_no_traceback(client: TestClient) -> None:
    run_id = sample_run(client)
    body = (DEFAULT_DATA_DIR / "in_pl_monthly.csv").read_bytes().replace(b"2024-04,", b"2023-04,", 1)
    assert client.put(f"/api/runs/{run_id}/files/in_pl_monthly.csv", content=body).json()["stored"] is True
    reply = client.post(f"/api/runs/{run_id}/analyse")
    assert reply.status_code == 422
    assert reply.json()["detail"].startswith("input rejected: in_pl_monthly.csv:2: column month: 2023-04")
    assert "Traceback" not in reply.text


def test_a_refused_file_leaves_its_slot_empty_and_nothing_earlier_stays_in_use(client: TestClient) -> None:
    run_id = finished_run(client)
    rates = (DEFAULT_DATA_DIR / "fx_rates.csv").read_bytes().replace(b"GBP,USD,closing,1.2530", b"GBP,USD,closing,-1")
    assert client.put(f"/api/runs/{run_id}/files/fx_rates.csv", content=rates).json()["stored"] is False
    meta = client.get(f"/api/runs/{run_id}").json()
    row = next(f for f in meta["files"] if f["name"] == "fx_rates.csv")
    assert row["present"] is False and row["rejected"] is True and "greater than zero" in row["error"]
    assert meta["status"] == "new"
    assert client.post(f"/api/runs/{run_id}/analyse").status_code == 409
    good = (DEFAULT_DATA_DIR / "fx_rates.csv").read_bytes()
    assert client.put(f"/api/runs/{run_id}/files/fx_rates.csv", content=good).json()["stored"] is True
    again = next(f for f in client.get(f"/api/runs/{run_id}").json()["files"] if f["name"] == "fx_rates.csv")
    assert again["present"] is True and not again.get("rejected")
