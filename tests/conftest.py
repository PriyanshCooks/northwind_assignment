"""Shared fixtures: the supplied data parsed once, and a helper that builds a context from an edited copy of it."""
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from app.domain.runs import Context
from app.services.run_service import build_context
from app.utils.paths import DEFAULT_DATA_DIR


@pytest.fixture(scope="session")
def ctx() -> Context:
    return build_context(DEFAULT_DATA_DIR)


@pytest.fixture
def edited_context(tmp_path: Path) -> Callable[[str, str, str], Context]:
    """Copy the data, replace `old` with `new` in one file, and build a context from the copy."""

    def build(file: str, old: str, new: str) -> Context:
        data = tmp_path / "data"
        shutil.copytree(DEFAULT_DATA_DIR, data, dirs_exist_ok=True)
        target = data / file
        text = target.read_bytes().decode("utf-8")
        newline = "\r\n" if "\r\n" in text else "\n"
        old, new = old.replace("\n", newline), new.replace("\n", newline)
        assert old in text, f"{old!r} not found in {file}"
        target.write_bytes(text.replace(old, new, 1).encode("utf-8"))
        return build_context(data)

    return build
