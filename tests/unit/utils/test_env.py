import os
from pathlib import Path

import pytest

from app.utils.env import load_env, scrub


def test_a_variable_already_in_the_environment_is_never_overridden(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / ".env").write_text("OPENAI_API_KEY=from-file\nNORTHWIND_TEST_X=2\n", encoding="utf-8")
    monkeypatch.setenv("OPENAI_API_KEY", "from-shell")
    monkeypatch.delenv("NORTHWIND_TEST_X", raising=False)
    load_env(tmp_path / ".env")
    assert os.environ["OPENAI_API_KEY"] == "from-shell"
    assert os.environ["NORTHWIND_TEST_X"] == "2"
    monkeypatch.delenv("NORTHWIND_TEST_X")


def test_empty_values_comments_and_a_missing_file_change_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    (tmp_path / ".env").write_text("# paste the key below\nOPENAI_API_KEY=\n", encoding="utf-8")
    load_env(tmp_path / ".env")
    load_env(tmp_path / "absent.env")
    assert "OPENAI_API_KEY" not in os.environ


def test_scrub_hides_key_shaped_text_and_the_exact_environment_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_API_KEY", "plainsecretvalue123")
    text = "401 Incorrect API key sk-proj-FAKEAbC123_xyz-9876 sent as Bearer abcdef.123456 and plainsecretvalue123"
    assert scrub(text) == "401 Incorrect API key [hidden] sent as [hidden] and [hidden]"
