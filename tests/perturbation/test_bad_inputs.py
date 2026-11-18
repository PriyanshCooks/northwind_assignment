"""Impossible inputs stop the run before any figure, with the file, the line and the column named."""
import pytest

from app.detectors.registry import run_all
from app.parsers.contracts import ContractError
from app.services.run_service import stage
from tests.conftest import Edit

CLOSING = "GBP,USD,closing,1.2530,2024-12-31,USD per 1 GBP"
JOURNAL_LINE = '"debit": "85000.00",\n          "credit": "0.00"'
CASES = [
    ("rate is zero", "fx_rates.csv", CLOSING, CLOSING.replace("1.2530", "0"), 6, "must be greater than zero"),
    ("rate is negative", "fx_rates.csv", CLOSING, CLOSING.replace("1.2530", "-1.2530"), 6, "must be greater than zero"),
    ("rate is text", "fx_rates.csv", CLOSING, CLOSING.replace("1.2530", "abc"), 6, "column rate: not a decimal"),
    ("rate is empty", "fx_rates.csv", CLOSING, CLOSING.replace("1.2530", ""), 6, "column rate: missing"),
    ("rate is NaN", "fx_rates.csv", CLOSING, CLOSING.replace("1.2530", "NaN"), 6, "not a finite number"),
    ("rate is infinite", "fx_rates.csv", CLOSING, CLOSING.replace("1.2530", "Infinity"), 6, "not a finite number"),
    ("rate row repeated with another value", "fx_rates.csv", CLOSING,
     CLOSING + "\n" + CLOSING.replace("1.2530", "1.3000"), 7, "conflicts with (1.2530 against 1.3000) line 6"),
    ("rate row repeated as it was", "fx_rates.csv", CLOSING, CLOSING + "\n" + CLOSING, 7, "repeats line 6"),
    ("closing rate dated before year end", "fx_rates.csv", CLOSING, CLOSING.replace("2024-12-31", "2024-11-30"), 6,
     "a closing rate is dated 2024-12-31"),
    ("ownership is zero", "entities.csv", "GBP,100,", "GBP,0,", 3, "0 is outside 0 to 100 percent"),
    ("ownership is above 100", "entities.csv", "INR,80,", "INR,120,", 4, "120 is outside 0 to 100 percent"),
    ("interest in the note is above 100", "acquisition_note.md", "80% of", "120% of", 4, "120 is outside"),
    ("trial balance line with debit and credit", "tb_us.csv", "4875000.00,0.00", "4875000.00,5.00", 2,
     "debit and credit: both are filled"),
    ("trial balance amount is text", "tb_us.csv", "4875000.00,0.00", "4875000.00,x", 2, "column credit: not a decimal"),
    ("journal line with debit and credit", "adjustments.json", JOURNAL_LINE, JOURNAL_LINE.replace('"0.00"', '"5.00"'),
     14, "debit and credit: both are filled"),
    ("journal amount is text", "adjustments.json", JOURNAL_LINE, JOURNAL_LINE.replace("85000.00", "abc"), 14,
     "column debit: not a decimal"),
    ("india month outside the year", "in_pl_monthly.csv", "2024-04,65600000.00", "2023-04,65600000.00", 2,
     "column month: 2023-04"),
    ("invoice dated outside the year", "intercompany.csv", "2024-03-31,USD,157460.00", "2023-03-31,USD,157460.00", 2,
     "column doc_date: 2023-03-31"),
    ("the India entity row is deleted", "entities.csv",
     "IN,Northwind India Pvt Ltd,India,INR,80,2024-07-01,31-Mar,Tally Prime,tb_in.csv", "", 1,
     "missing from the file: IN"),
    ("the acquisition date is not a date", "entities.csv", "2024-07-01", "2024-07--1", 4, "not a date"),
    ("opening share capital row is deleted", "prior_year_group.csv",
     "3100,Share capital,1250000.00,2023-12-31,Parent share capital at historical rate" + chr(10), "", 1,
     "missing: 3100"),
    ("a month that is not a month", "in_pl_monthly.csv", "2024-04,65600000.00", "2024--4,65600000.00", 2,
     "not a year and month"),
]


@pytest.mark.parametrize(("case", "file", "old", "new", "line", "reason"), CASES, ids=[c[0] for c in CASES])
def test_the_run_stops_and_names_the_place(
    edited_context: Edit, case: str, file: str, old: str, new: str, line: int, reason: str,
) -> None:
    with pytest.raises(ContractError) as caught:
        edited_context(file, old, new)
    assert (caught.value.file, caught.value.line) == (file, line)
    assert reason in caught.value.reason


MISSING_MAP_ROW = "4000,Sales,4100\n"


def test_a_deleted_map_row_is_a_finding_and_a_failed_check_never_a_crash(edited_context: Edit) -> None:
    run = stage(edited_context("map_uk.csv", MISSING_MAP_ROW, ""))
    assert any(f.code == "D02" for f in run.findings)
    assert any(c.name.startswith("oracle") and not c.ok for c in run.checks)


def test_an_invoice_listed_twice_is_flagged(edited_context: Edit) -> None:
    again = "US,UK,INV-US-2201,2024-03-31,USD,157460.00,USD,157460.00,Management fee\n"
    ctx = edited_context("intercompany.csv", "US,UK,INV-US-2224", again + "US,UK,INV-US-2224")
    assert any(f.code == "D11" and f.key.endswith(":duplicate") for f in run_all(ctx))


def test_a_side_of_an_invoice_that_disagrees_is_flagged(edited_context: Edit) -> None:
    ctx = edited_context("intercompany.csv", "UK,US,INV-US-2201,2024-03-31,USD,157460.00",
                         "UK,US,INV-US-2201,2024-03-31,USD,-157460.00")
    assert any(f.code == "D11" and f.key.endswith(":mismatch") for f in run_all(ctx))
