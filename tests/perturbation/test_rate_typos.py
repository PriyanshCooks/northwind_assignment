"""Rates that are possible but wrong, or absent. The run does not stop on a typo it cannot prove; it flags it amber.
The rejected cases (zero, negative, text, empty, duplicates, ownership, debit and credit) are in test_bad_inputs."""
from decimal import Decimal

from app.domain.figures import Unknown
from app.services.run_service import Consolidation, stage
from app.utils.money import round2
from tests.conftest import Edit

CLOSING = "GBP,USD,closing,1.2530,2024-12-31,USD per 1 GBP"
KEYS = ["D15:fx_rates.csv:6:closing_neighbours", "D15:tb_uk.csv:10:closing_vs_booked"]


def run_with(edited_context: Edit, new: str) -> Consolidation:
    return stage(edited_context("fx_rates.csv", CLOSING + "\n", new))


def amber(run: Consolidation) -> dict[str, str]:
    return {f.key: f.severity for f in run.findings if f.code == "D15"}


def total_assets(run: Consolidation) -> Decimal:
    return round2(Decimal(str(run.figures["total_assets"].value)))  # type: ignore[union-attr]


def test_a_closing_rate_100_times_too_big_runs_on_and_is_flagged_amber(edited_context: Edit) -> None:
    run = run_with(edited_context, "GBP,USD,closing,125.30,2024-12-31,USD per 1 GBP\n")
    assert run.blocked is None and run.checks_passed
    assert amber(run) == dict.fromkeys(KEYS, "FLAG")
    assert total_assets(run) == Decimal("6045186.63")


def test_an_inverted_closing_rate_runs_on_and_is_flagged_amber(edited_context: Edit) -> None:
    run = run_with(edited_context, "GBP,USD,closing,0.7981,2024-12-31,USD per 1 GBP\n")
    assert run.blocked is None and run.checks_passed
    assert amber(run) == dict.fromkeys(KEYS, "FLAG")
    assert total_assets(run) == Decimal("41546656.07")


def test_a_removed_closing_rate_blocks_and_every_figure_is_unknown_with_a_reason(edited_context: Edit) -> None:
    run = run_with(edited_context, "")
    assert run.blocked == "US cannot be translated: no USD closing rate in fx_rates.csv"
    assert amber(run) == {}
    assert isinstance(run.figures["total_assets"], Unknown) and run.figures["total_assets"].reason
