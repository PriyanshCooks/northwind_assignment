import shutil
from pathlib import Path

import pytest

from app.services.whatif_service import Change, diff_inputs, impact, patched_copy, whatif
from app.utils.hashing import sha256_file
from app.utils.paths import DEFAULT_DATA_DIR

CLOSING_ROW = 6  # fx_rates.csv: GBP/USD closing, line 6 counting the header


def test_a_changed_closing_rate_moves_the_balance_sheet_figures() -> None:
    diff = whatif(DEFAULT_DATA_DIR, Change(patches=[f"fx_rates.csv:{CLOSING_ROW}.rate=1.30"]))
    assert {"total_assets", "goodwill_closing", "nci_closing", "translation_reserve_movement"} <= set(diff.figures)
    assert diff.figures["total_assets"] == ("28575272.95", "27752495.90")


def test_adding_a_sgd_closing_rate_turns_the_null_into_a_number() -> None:
    row = "fx_rates.csv=GBP,SGD,closing,1.7300,2024-12-31,SGD per 1 GBP"
    before, after = whatif(DEFAULT_DATA_DIR, Change(appends=[row])).figures["sgd_bank_gbp"]
    assert before.startswith("null (") and after == "23121.39"


def test_the_supplied_files_are_never_touched() -> None:
    before = {p.name: sha256_file(p) for p in DEFAULT_DATA_DIR.iterdir() if p.is_file()}
    whatif(DEFAULT_DATA_DIR, Change(patches=[f"fx_rates.csv:{CLOSING_ROW}.rate=1.30"]))
    assert before == {p.name: sha256_file(p) for p in DEFAULT_DATA_DIR.iterdir() if p.is_file()}


def test_a_patch_keeps_the_line_endings_of_the_file(tmp_path: Path) -> None:
    patched_copy(DEFAULT_DATA_DIR, tmp_path, Change(patches=[f"fx_rates.csv:{CLOSING_ROW}.rate=1.30"]))
    original = (DEFAULT_DATA_DIR / "fx_rates.csv").read_bytes()
    changed = (tmp_path / "fx_rates.csv").read_bytes()
    assert changed.count(b"\r\n") == original.count(b"\r\n") and changed != original


def test_an_unknown_column_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="no column"):
        patched_copy(DEFAULT_DATA_DIR, tmp_path, Change(patches=["fx_rates.csv:6.price=1"]))


def test_an_assumption_can_be_set_for_one_run() -> None:
    diff = whatif(DEFAULT_DATA_DIR, Change(sets=["je017=post"]))
    assert "group_profit" in diff.figures


def test_impact_lists_the_figures_a_rate_row_feeds() -> None:
    assert "total_assets" in impact(DEFAULT_DATA_DIR, f"fx_rates.csv:{CLOSING_ROW}").figures


def test_diff_inputs_names_the_changed_file_and_line(tmp_path: Path) -> None:
    shutil.copytree(DEFAULT_DATA_DIR, tmp_path / "old")
    patched_copy(DEFAULT_DATA_DIR, tmp_path / "new", Change(patches=[f"fx_rates.csv:{CLOSING_ROW}.rate=1.30"]))
    assert diff_inputs(tmp_path / "old", tmp_path / "new") == ["fx_rates.csv: changed at line(s) 6"]
    assert diff_inputs(tmp_path / "old", tmp_path / "old") == []


def test_a_typo_in_a_rate_shows_the_finding_it_raises() -> None:
    diff = whatif(DEFAULT_DATA_DIR, Change(patches=[f"fx_rates.csv:{CLOSING_ROW}.rate=125.30"]))
    assert any(key.startswith("D15") for key in diff.new_findings)
