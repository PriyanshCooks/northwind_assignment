from fastapi.testclient import TestClient

from app.utils.paths import DEFAULT_DATA_DIR
from tests.api.conftest import sample_run


def test_a_month_outside_the_year_gives_422_with_the_place_and_no_traceback(client: TestClient) -> None:
    run_id = sample_run(client)
    body = (DEFAULT_DATA_DIR / "in_pl_monthly.csv").read_bytes().replace(b"2024-04,", b"2023-04,", 1)
    assert client.put(f"/api/runs/{run_id}/files/in_pl_monthly.csv", content=body).json()["stored"] is True
    reply = client.post(f"/api/runs/{run_id}/analyse")
    assert reply.status_code == 422
    assert reply.json()["detail"].startswith("input rejected: in_pl_monthly.csv:2: column month: 2023-04")
    assert "Traceback" not in reply.text
