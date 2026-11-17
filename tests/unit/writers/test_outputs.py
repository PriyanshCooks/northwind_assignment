import csv
import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.cli import main
from app.domain.runs import Context
from app.services.run_service import Consolidation, run_consolidation
from app.services.trace_service import trace
from app.utils.paths import DEFAULT_DATA_DIR
from tests.conftest import Edit

BRIEF_KEYS = [
    "group_revenue", "group_profit", "profit_owners", "profit_nci", "nci_closing", "goodwill_closing",
    "translation_reserve_movement", "total_assets", "total_equity", "intercompany_difference",
    "sgd_bank_gbp", "journals",
]


@pytest.fixture(scope="module")
def outputs(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path, Consolidation]:
    base = tmp_path_factory.mktemp("run")
    run = run_consolidation(DEFAULT_DATA_DIR, base / "out", base / "run.db")
    return base / "out", base / "run.db", run


def read(out: Path, name: str):
    return json.loads((out / name).read_text(encoding="utf-8"), parse_float=Decimal)


def test_every_required_output_is_written(outputs) -> None:
    out, _, _ = outputs
    names = {p.name for p in out.iterdir()}
    assert {"consolidated_tb.csv", "balance_sheet.json", "profit_and_loss.json", "changes_in_equity.json",
            "eliminations.csv", "issues.json", "control_figures_pb.json", "run_manifest.json"} <= names


def test_control_figures_file_has_exactly_the_twelve_keys_in_order(outputs) -> None:
    out, _, _ = outputs
    assert list(read(out, "control_figures_pb.json")) == BRIEF_KEYS


def test_control_figures_values_are_numbers_or_null(outputs) -> None:
    out, _, _ = outputs
    figures = read(out, "control_figures_pb.json")
    assert figures["goodwill_closing"] == Decimal("1375815.07") and figures["sgd_bank_gbp"] is None
    assert figures["journals"] == {"posted": 15, "rejected": 3, "held": 2}


def test_status_file_says_why_the_sgd_figure_is_null(outputs) -> None:
    out, _, _ = outputs
    status = read(out, "control_figures_status.json")["figures"]
    assert "no GBP/SGD closing rate" in status["sgd_bank_gbp"]["reason"]
    assert status["total_assets"]["status"] == "provisional"


def test_consolidated_tb_balances_to_a_few_cents_and_every_row_has_sources(outputs) -> None:
    out, _, _ = outputs
    rows = list(csv.DictReader((out / "consolidated_tb.csv").open(encoding="utf-8")))
    debit = sum(Decimal(r["debit_gbp"] or 0) for r in rows)
    credit = sum(Decimal(r["credit_gbp"] or 0) for r in rows)
    assert abs(debit - credit) < Decimal("0.10")
    assert all(r["source_rows"] for r in rows)


def test_a_consolidated_line_cites_the_trial_balance_rows_it_came_from(outputs) -> None:
    out, _, _ = outputs
    rows = csv.DictReader((out / "consolidated_tb.csv").open(encoding="utf-8"))
    row = next(r for r in rows if r["group_code"] == "4100")
    assert "tb_us.csv:18" in row["source_rows"] and "tb_uk.csv:16" in row["source_rows"]


def test_every_elimination_entry_balances_to_the_cent(outputs) -> None:
    out, _, _ = outputs
    totals: dict[str, Decimal] = {}
    for r in csv.DictReader((out / "eliminations.csv").open(encoding="utf-8")):
        signed = Decimal(r["debit"] or 0) - Decimal(r["credit"] or 0)
        totals[r["entry_id"]] = totals.get(r["entry_id"], Decimal(0)) + signed
    assert totals and all(abs(v) <= Decimal("0.02") for v in totals.values())


def test_issues_list_the_memo_with_file_line_and_what_was_done(outputs) -> None:
    out, _, _ = outputs
    issues = read(out, "issues.json")["issues"]
    memo = next(i for i in issues if i["code"] == "D12")
    assert (memo["file"], memo["line"], memo["action"]) == ("adjustments.json", 112, "flagged")
    assert all({"file", "line", "amount_affected", "action"} <= set(i) for i in issues)


def test_two_runs_give_byte_identical_outputs(outputs, tmp_path: Path) -> None:
    out, _, _ = outputs
    run_consolidation(DEFAULT_DATA_DIR, tmp_path / "again", tmp_path / "run.db")
    for path in out.iterdir():
        assert path.read_bytes() == (tmp_path / "again" / path.name).read_bytes(), path.name


def test_trace_walks_goodwill_down_to_the_acquisition_note_lines(outputs) -> None:
    _, db, _ = outputs
    text = "\n".join(trace(db, "goodwill_closing"))
    assert "acquisition_note.md:5" in text and "1375815.07" in text


def test_trace_walks_an_account_down_to_trial_balance_lines(outputs) -> None:
    _, db, _ = outputs
    assert any("tb_us.csv:2" in line for line in trace(db, "1100"))


def test_trace_of_an_unknown_target_says_so(outputs) -> None:
    _, db, _ = outputs
    assert "nothing recorded" in trace(db, "nonsense")[0]


def test_blocked_run_still_writes_issues_and_nulls(edited_context: Edit, tmp_path: Path) -> None:
    cash = "1100,Cash and cash equivalents,"
    ctx: Context = edited_context("tb_us.csv", cash + "4875000.00", cash + "4875001.00")
    run = run_consolidation(ctx.inputs.data_dir, tmp_path / "out", tmp_path / "run.db")
    figures = json.loads((tmp_path / "out" / "control_figures_pb.json").read_text(encoding="utf-8"))
    assert run.blocked and all(v is None for v in figures.values())
    assert any(i["code"] == "RUN" for i in json.loads((tmp_path / "out" / "issues.json").read_text())["issues"])


def test_check_command_passes_on_the_supplied_data(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["check"]) == 0
    assert "bundle intact" in capsys.readouterr().out
