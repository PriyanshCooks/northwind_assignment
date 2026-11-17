"""The control figures file is checked against a strict schema, so a stray key, a string number or a bool fails."""
import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, StrictFloat, StrictInt, ValidationError

from app.core.figures import KEYS
from app.utils.paths import DEFAULT_DATA_DIR
from tests.conftest import Edit
from tests.helpers import run_pipeline

Number = StrictFloat | StrictInt | None


class Journals(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    posted: StrictInt
    rejected: StrictInt
    held: StrictInt


class ControlFigures(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    group_revenue: Number
    group_profit: Number
    profit_owners: Number
    profit_nci: Number
    nci_closing: Number
    goodwill_closing: Number
    translation_reserve_movement: Number
    total_assets: Number
    total_equity: Number
    intercompany_difference: Number
    sgd_bank_gbp: Number
    journals: Journals | None


def _read(folder: Path, name: str) -> dict[str, object]:
    return json.loads((folder / name).read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def test_the_supplied_data_gives_a_file_that_passes_the_strict_schema(tmp_path: Path) -> None:
    run_pipeline(DEFAULT_DATA_DIR, tmp_path / "out", tmp_path / "run.db", tmp_path / "logs")
    figures = ControlFigures.model_validate(_read(tmp_path / "out", "control_figures_pb.json"))
    assert figures.sgd_bank_gbp is None and figures.journals == Journals(posted=15, rejected=3, held=2)


def test_every_null_has_a_reason_in_the_status_file(tmp_path: Path) -> None:
    run_pipeline(DEFAULT_DATA_DIR, tmp_path / "out", tmp_path / "run.db", tmp_path / "logs")
    out = tmp_path / "out"
    values, status = _read(out, "control_figures_pb.json"), _read(out, "control_figures_status.json")
    assert list(values) == list(KEYS)
    for key, value in values.items():
        entry = status["figures"][key]  # type: ignore[index]
        assert (value is None) == (entry["status"] == "unknown")
        assert entry["status"] != "unknown" or entry["reason"]
        assert entry["status"] != "provisional" or entry["open_items"]


def test_a_blocked_run_still_passes_the_schema_with_every_figure_null(edited_context: Edit, tmp_path: Path) -> None:
    cash = "1100,Cash and cash equivalents,"
    ctx = edited_context("tb_us.csv", cash + "4875000.00", cash + "4875001.00")
    run_pipeline(ctx.inputs.data_dir, tmp_path / "out", tmp_path / "run.db", tmp_path / "logs")
    figures = ControlFigures.model_validate(_read(tmp_path / "out", "control_figures_pb.json"))
    assert all(v is None for v in figures.model_dump().values())


def test_the_schema_rejects_a_string_number_and_an_extra_key() -> None:
    good = {k: None for k in KEYS}
    for bad in ({**good, "group_revenue": "1.0"}, {**good, "extra": 1}):
        try:
            ControlFigures.model_validate(bad)
        except ValidationError:
            continue
        raise AssertionError(f"accepted {bad}")
