"""Change one input at a time and check that the invariants and the oracle still hold and that the figure moves as
predicted by hand. A hardcoded constant or a missed rate shows up as a failed check or a wrong shift."""
from decimal import Decimal
from pathlib import Path

import pytest

from app.domain.figures import Determined, Provisional, Unknown
from app.services.run_service import Consolidation, build_context, stage
from app.services.whatif_service import Change, patched_copy
from app.utils.money import round2
from app.utils.paths import CONFIG_DIR, DEFAULT_DATA_DIR

AVERAGE, CLOSING = 3, 6  # fx_rates.csv lines: GBP/USD average and closing
INR_FULL_YEAR, INR_H2, INR_CLOSING = 8, 9, 11  # USD/INR average, H2 average, closing


def perturbed(tmp_path: Path, **change: list[str]) -> Consolidation:
    patched_copy(DEFAULT_DATA_DIR, tmp_path / "data", Change(**change))
    return stage(build_context(tmp_path / "data", CONFIG_DIR))


def value(run: Consolidation, key: str) -> Decimal:
    figure = run.figures[key]
    assert isinstance(figure, (Determined, Provisional)) and isinstance(figure.value, Decimal)
    return figure.value


def failed(run: Consolidation) -> list[str]:
    return [c.name for c in run.checks if not c.ok]


@pytest.fixture(scope="module")
def base() -> Consolidation:
    return stage(build_context(DEFAULT_DATA_DIR, CONFIG_DIR))


def test_more_us_revenue_adds_that_revenue_at_the_average_rate(tmp_path: Path, base: Consolidation) -> None:
    run = perturbed(tmp_path, patches=["tb_us.csv:18.credit=18401000.00", "tb_us.csv:2.debit=4876000.00"])
    expected = round2(Decimal("1000") / Decimal("1.2780"))
    assert round2(value(run, "group_revenue") - value(base, "group_revenue")) == expected
    assert round2(value(run, "group_profit") - value(base, "group_profit")) == expected
    assert failed(run) == []


RATES = [(AVERAGE, "1.2780"), (CLOSING, "1.2530"), (INR_H2, "83.95"), (INR_CLOSING, "85.62")]


@pytest.mark.parametrize("line,old", RATES)
def test_every_rate_change_keeps_the_invariants_and_the_oracle(tmp_path: Path, base: Consolidation,
                                                                line: int, old: str) -> None:
    run = perturbed(tmp_path, patches=[f"fx_rates.csv:{line}.rate={Decimal(old) * Decimal('1.05'):.4f}"])
    assert failed(run) == []
    assert run.figures != base.figures


def test_the_full_year_inr_rate_feeds_no_figure_because_india_uses_the_h2_average(tmp_path: Path,
                                                                                  base: Consolidation) -> None:
    run = perturbed(tmp_path, patches=[f"fx_rates.csv:{INR_FULL_YEAR}.rate=87.8640"])
    assert run.figures == base.figures


def test_a_new_sgd_closing_rate_restates_the_bank_balance_but_the_oracle_cannot_follow(tmp_path: Path) -> None:
    """Known gap: the oracle keeps the SGD bank at its booked value, so it is off by exactly 40,000/1.73 - 23,010."""
    run = perturbed(tmp_path, appends=["fx_rates.csv=GBP,SGD,closing,1.7300,2024-12-31,SGD per 1 GBP"])
    assert round2(value(run, "sgd_bank_gbp")) == Decimal("23121.39")
    assert set(failed(run)) == {"oracle: group_profit", "oracle: profit_owners", "oracle: total_assets",
                                "oracle: total_equity"}
    assert round2(Decimal("40000") / Decimal("1.7300") - Decimal("23010")) == Decimal("111.39")


def test_a_bigger_intercompany_invoice_moves_the_difference_and_still_nets_to_zero(tmp_path: Path,
                                                                                   base: Consolidation) -> None:
    run = perturbed(tmp_path, patches=["intercompany.csv:2.doc_amount=167460.00",
                                       "intercompany.csv:2.booked_amount=167460.00"])
    assert value(run, "intercompany_difference") != value(base, "intercompany_difference")
    assert "intercompany balances and income net to zero" not in failed(run)


def test_an_unbalanced_trial_balance_makes_every_figure_null_with_a_reason(tmp_path: Path) -> None:
    run = perturbed(tmp_path, patches=["tb_us.csv:2.debit=4875001.00"])
    assert run.blocked
    assert all(isinstance(f, Unknown) and f.reason for f in run.figures.values())


def test_posting_the_rejected_journal_changes_profit_and_keeps_every_invariant(
        tmp_path: Path, base: Consolidation) -> None:
    patched_copy(DEFAULT_DATA_DIR, tmp_path / "data", Change())
    ctx = build_context(tmp_path / "data", CONFIG_DIR)
    ctx.assumptions["je017"] = "post"
    run = stage(ctx)
    assert value(run, "group_profit") != value(base, "group_profit")
    assert [n for n in failed(run) if not n.startswith("oracle:")] == []  # the oracle always rejects JE-017


def test_removing_a_needed_rate_stops_the_run_instead_of_guessing(tmp_path: Path) -> None:
    patched_copy(DEFAULT_DATA_DIR, tmp_path / "data", Change())
    path = tmp_path / "data" / "fx_rates.csv"
    lines = path.read_bytes().decode("utf-8").splitlines(keepends=True)
    del lines[CLOSING - 1]
    path.write_bytes("".join(lines).encode("utf-8"))
    run = stage(build_context(tmp_path / "data", CONFIG_DIR))
    assert run.blocked or all(isinstance(f, Unknown) for f in run.figures.values()) or failed(run)


def test_a_closing_rate_that_leaves_a_repeating_decimal_still_balances_the_eliminations(tmp_path: Path) -> None:
    """Found by the property test: at closing 1.4000 an elimination is off by about 1e-48, which is rounding."""
    run = perturbed(tmp_path, patches=[f"fx_rates.csv:{CLOSING}.rate=1.4000"])
    assert failed(run) == []
