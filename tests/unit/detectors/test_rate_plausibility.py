from app.detectors.registry import run_all
from app.domain.findings import Finding
from app.domain.runs import Context
from tests.conftest import Edit

CLOSING = "GBP,USD,closing,1.2530,2024-12-31,USD per 1 GBP"
SGD_AVERAGE = "GBP,SGD,average,1.7120,FY2024,SGD per 1 GBP"


def d15(ctx: Context, kind: str = "") -> list[Finding]:
    return [f for f in run_all(ctx) if f.code == "D15" and f.key.endswith(kind)]


def test_the_supplied_rates_raise_nothing(ctx: Context) -> None:
    assert d15(ctx) == []


def test_a_closing_rate_100_times_too_big_is_flagged_amber_with_its_working(edited_context: Edit) -> None:
    (finding,) = d15(edited_context("fx_rates.csv", CLOSING, CLOSING.replace("1.2530", "125.30")), "_neighbours")
    assert (finding.key, finding.severity) == ("D15:fx_rates.csv:6:closing_neighbours", "FLAG")
    assert "median of the 4 other GBP/USD rates" in finding.claim and "tolerance is 10%" in finding.claim


def test_the_same_bad_rate_also_disagrees_with_the_booked_usd_payable(edited_context: Edit) -> None:
    (finding,) = d15(edited_context("fx_rates.csv", CLOSING, CLOSING.replace("1.2530", "125.30")), "_vs_booked")
    assert finding.file == "tb_uk.csv" and "implies" in finding.claim


def test_an_inverted_closing_rate_is_flagged(edited_context: Edit) -> None:
    (finding,) = d15(edited_context("fx_rates.csv", CLOSING, CLOSING.replace("1.2530", "0.7981")), "_neighbours")
    assert finding.line == 6 and "0.7981" in finding.claim


def test_an_sgd_closing_rate_far_from_the_booked_amount_is_flagged(edited_context: Edit) -> None:
    row = "GBP,SGD,closing,17.384,2024-12-31,SGD per 1 GBP"
    (finding,) = d15(edited_context("fx_rates.csv", SGD_AVERAGE, SGD_AVERAGE + "\n" + row), "_vs_booked")
    assert finding.key.endswith("closing_vs_booked") and finding.file == "tb_uk.csv"
    assert "implies 1.7384 SGD per GBP" in finding.claim


def test_an_sgd_closing_rate_near_the_booked_amount_raises_nothing(edited_context: Edit) -> None:
    row = "GBP,SGD,closing,1.7400,2024-12-31,SGD per 1 GBP"
    assert d15(edited_context("fx_rates.csv", SGD_AVERAGE, SGD_AVERAGE + "\n" + row)) == []
