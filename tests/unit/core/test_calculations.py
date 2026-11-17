"""Every output row and control figure carries a formula that code can re-run from its own inputs."""
from decimal import Decimal

import pytest

from app.core.calculations import calculation_records
from app.domain.calculations import CalcRecord
from app.domain.figures import Determined, Provisional
from app.domain.runs import Context
from app.services.run_service import Consolidation, stage
from app.verification.recalc import evaluate, failures
from app.writers.consolidated_tb import tb_rows


@pytest.fixture(scope="module")
def run(ctx: Context) -> Consolidation:
    return stage(ctx)


@pytest.fixture(scope="module")
def records(run: Consolidation) -> list[CalcRecord]:
    return calculation_records(run)


def test_every_formula_reproduces_its_result(records: list[CalcRecord]) -> None:
    assert failures(records) == []


def test_there_is_one_row_record_per_consolidated_row(run: Consolidation, records: list[CalcRecord]) -> None:
    rows = {r.id: r for r in records if r.kind == "row"}
    assert set(rows) == {f"row:{account}" for account, _, _, _ in tb_rows(run)}
    for account, _, amount, _ in tb_rows(run):
        assert abs(rows[f"row:{account}"].result - amount) <= Decimal("1e-9")


def test_figure_records_equal_the_figures(run: Consolidation, records: list[CalcRecord]) -> None:
    by_id = {r.id: r for r in records}
    for key, figure in run.figures.items():
        if key == "journals" or not isinstance(figure, (Determined, Provisional)):
            continue
        assert by_id[f"fig:{key}"].result == figure.value


def test_the_unknown_sgd_figure_has_no_record(records: list[CalcRecord]) -> None:
    assert "fig:sgd_bank_gbp" not in {r.id for r in records}


def test_goodwill_inputs_name_the_acquisition_note_lines(records: list[CalcRecord]) -> None:
    goodwill = next(r for r in records if r.id == "fig:goodwill_closing")
    sources = {i.name: i.source for i in goodwill.inputs}
    assert sources["consideration"].startswith("acquisition_note.md:")
    assert sources["closing_rate"].startswith("closing fx_rates.csv:")


def test_a_wrong_result_is_caught(records: list[CalcRecord]) -> None:
    good = next(r for r in records if r.id == "fig:group_revenue")
    bad = good.model_copy(update={"result": good.result + 1})
    assert failures([bad]) == [bad.id] and evaluate(good) == good.result


def test_a_formula_with_a_call_is_refused(records: list[CalcRecord]) -> None:
    sneaky = records[0].model_copy(update={"formula": "__import__('os').getcwd()"})
    with pytest.raises(ValueError):
        evaluate(sneaky)
