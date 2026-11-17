"""The static page is served by the same process, and server text never goes into the page as HTML."""
from pathlib import Path

from fastapi.testclient import TestClient

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def test_the_ui_is_served_at_ui_and_root_redirects(client: TestClient) -> None:
    page = client.get("/ui/")
    assert page.status_code == 200 and "Northwind consolidation review" in page.text
    assert client.get("/ui/app.js").status_code == 200 and client.get("/ui/steps.js").status_code == 200
    assert client.get("/ui/format.js").status_code == 200
    assert client.get("/", follow_redirects=False).headers["location"] == "/ui/"


def test_the_scripts_never_write_server_text_as_html() -> None:
    for path in FRONTEND.glob("*.js"):
        text = path.read_text(encoding="utf-8")
        assert "innerHTML" not in text and "outerHTML" not in text and "insertAdjacentHTML" not in text


def test_no_build_step_files_exist() -> None:
    assert not (FRONTEND / "package.json").exists() and not (FRONTEND / "node_modules").exists()
