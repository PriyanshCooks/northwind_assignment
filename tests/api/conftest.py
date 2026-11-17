"""A test client over a scratch runs folder, so no test touches .northwind/."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(tmp_path / "runs"))


def sample_run(client: TestClient) -> str:
    return str(client.post("/api/runs", json={"name": "sample", "use_sample": True}).json()["id"])


def finished_run(client: TestClient, approver: str = "tester") -> str:
    """Create a run on the supplied data, analyse it and approve whatever is waiting."""
    run_id = sample_run(client)
    meta = client.post(f"/api/runs/{run_id}/analyse").json()
    if meta["status"] == "awaiting_review":
        decisions = {t: "approve" for t in meta["open_items"]}
        meta = client.post(f"/api/runs/{run_id}/decisions", json={"approver": approver, "decisions": decisions}).json()
    assert meta["status"] == "done"
    return run_id
