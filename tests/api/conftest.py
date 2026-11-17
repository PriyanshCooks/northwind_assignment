"""A test client over a scratch runs folder, so no test touches .northwind/."""
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(tmp_path / "runs"), base_url="http://127.0.0.1")


def sample_run(client: TestClient) -> str:
    return str(client.post("/api/runs", json={"name": "sample", "use_sample": True}).json()["id"])


def settle(client: TestClient, meta: dict[str, Any], approver: str = "tester") -> dict[str, Any]:
    """Approve whatever a run is waiting on, so tests about later steps start from a finished run."""
    if meta["status"] == "awaiting_review":
        decisions = {t: "approve" for t in meta["open_items"]}
        body = {"approver": approver, "decisions": decisions}
        meta = client.post(f"/api/runs/{meta['id']}/decisions", json=body).json()
    return meta


def finished_run(client: TestClient, approver: str = "tester") -> str:
    """Create a run on the supplied data, analyse it and approve whatever is waiting."""
    run_id = sample_run(client)
    meta = client.post(f"/api/runs/{run_id}/analyse").json()
    if meta["status"] == "awaiting_review":
        decisions = {t: "approve" for t in meta["open_items"]}
        meta = client.post(f"/api/runs/{run_id}/decisions", json={"approver": approver, "decisions": decisions}).json()
    assert meta["status"] == "done"
    return run_id
