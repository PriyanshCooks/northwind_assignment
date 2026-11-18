"""A crash in the middle of appending leaves a cut-off last line. It must not stop every later run."""
import json
from pathlib import Path

import pytest

from app.llm.ledger import Ledger


def test_a_cut_off_last_line_is_ignored_and_the_earlier_calls_still_replay(tmp_path: Path) -> None:
    path = tmp_path / "l.jsonl"
    path.write_text(json.dumps({"key": "a", "validated": True}) + "\n" + '{"key": "b", "vali', encoding="utf-8")
    ledger = Ledger(path)
    assert ledger.get("a") is not None and ledger.get("b") is None


def test_a_damaged_line_in_the_middle_is_still_an_error(tmp_path: Path) -> None:
    path = tmp_path / "l.jsonl"
    path.write_text('{"key": "a", "vali\n' + json.dumps({"key": "b"}) + "\n", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        Ledger(path)
