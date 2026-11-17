"""The server stays on this machine, never calls a model, and never shows the key."""
import json

import pytest
from fastapi.testclient import TestClient

from app import main
from tests.api.conftest import finished_run

SENTINEL = "sk-FAKE-0123456789abcdefghijklmnop"


def test_server_binds_to_loopback_only() -> None:
    assert main.HOST == "127.0.0.1"


def test_the_key_is_in_no_response_and_no_run_file(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", SENTINEL)
    run_id = finished_run(client)
    seen = [client.get(f"/api/runs/{run_id}/{p}").text for p in ("review", "results", "outputs")]
    seen += [json.dumps(client.get("/api/runs").json()), client.post(f"/api/runs/{run_id}/build").text]
    assert not any(SENTINEL in text for text in seen)
    root = client.app.state.registry.root  # type: ignore[attr-defined]
    assert not any(SENTINEL in p.read_text(encoding="utf-8", errors="ignore") for p in root.rglob("*") if p.is_file())


def test_review_never_reaches_a_model(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("a live model call was attempted")

    monkeypatch.setattr("app.llm.client.build_model", refuse)
    assert client.get(f"/api/runs/{finished_run(client)}/review").status_code == 200


def test_a_request_for_another_host_name_is_refused(client: TestClient) -> None:
    assert client.get("/api/runs", headers={"host": "evil.example"}).status_code == 400
    assert client.get("/api/runs", headers={"host": "localhost:8000"}).status_code == 200


def test_error_messages_carry_no_absolute_path() -> None:
    from app.main import scrub
    assert scrub(r"cannot read C:\Users\asus\run\data\tb_uk.csv now") == "cannot read tb_uk.csv now"
    assert scrub("missing /home/me/.northwind/runs/r1/run.json") == "missing run.json"
    assert scrub("GBP/USD has no rate") == "GBP/USD has no rate"


def test_an_unexpected_error_is_returned_without_a_path(client: TestClient) -> None:
    client.app.state.registry = None  # type: ignore[attr-defined]
    quiet = TestClient(client.app, base_url="http://127.0.0.1", raise_server_exceptions=False)
    response = quiet.get("/api/runs")
    assert response.status_code == 500 and ":\\" not in response.text
