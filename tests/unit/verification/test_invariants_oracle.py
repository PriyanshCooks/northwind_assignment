from decimal import Decimal

from app.domain.runs import Context
from app.services.run_service import Consolidation, stage
from app.utils.money import round2
from app.utils.paths import DEFAULT_DATA_DIR
from app.verification.oracle import recompute
from tests.conftest import Edit


def failed(run: Consolidation) -> list[str]:
    return [c.name for c in run.checks if not c.ok]


def test_every_invariant_and_oracle_check_passes_on_the_supplied_data(ctx: Context) -> None:
    run = stage(ctx)
    assert run.checks and failed(run) == []


def test_there_are_nine_invariants_and_eleven_oracle_checks(ctx: Context) -> None:
    names = [c.name for c in stage(ctx).checks]
    assert sum(n.startswith("oracle:") for n in names) == 11 and len(names) == 20


def test_the_oracle_recomputes_the_figures_from_the_raw_files_alone() -> None:
    expected = recompute(DEFAULT_DATA_DIR)
    assert round2(expected["group_profit"]) == Decimal("2768780.95")  # type: ignore[arg-type]
    assert round2(expected["goodwill_closing"]) == Decimal("1375815.07")  # type: ignore[arg-type]
    assert expected["journals"] == {"posted": 15, "rejected": 3, "held": 2}


def test_the_oracle_notices_when_the_remap_assumption_is_off() -> None:
    on, off = recompute(DEFAULT_DATA_DIR, True), recompute(DEFAULT_DATA_DIR, False)
    assert round2(off["group_revenue"] - on["group_revenue"]) == Decimal("180000.00")  # type: ignore[operator]


def test_an_unbalanced_us_trial_balance_blocks_the_run_instead_of_producing_numbers(edited_context: Edit) -> None:
    cash = "1100,Cash and cash equivalents,"
    run = stage(edited_context("tb_us.csv", cash + "4875000.00", cash + "4875001.00"))
    assert run.blocked is not None and run.checks == []


def test_a_wrong_opening_rate_is_caught_by_the_reserve_check_and_the_oracle(edited_context: Edit) -> None:
    run = stage(edited_context("fx_rates.csv", "GBP,USD,opening,1.2730", "GBP,USD,opening,1.2830"))
    assert run.blocked is None
    assert "the two reserve routes agree" in failed(run)
    assert "oracle: translation_reserve_movement" in failed(run)
    assert not run.checks_passed
