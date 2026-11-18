from collections import Counter
from collections.abc import Callable
from decimal import Decimal

from app.detectors.registry import run_all
from app.domain.findings import Finding
from app.domain.runs import Context

Edit = Callable[[str, str, str], Context]


def by_code(ctx: Context, code: str, field: str = "") -> list[Finding]:
    return [f for f in run_all(ctx) if f.code == code and f.key.endswith(field)]


def test_every_known_defect_gives_exactly_one_finding(ctx: Context) -> None:
    counts = Counter(f.code for f in run_all(ctx))
    assert dict(counts) == {
        "D02": 1, "D03": 1, "D04": 1, "D05": 1, "D06": 1, "D07": 1, "D08": 1, "D09": 2, "D11": 1, "D12": 1, "D13": 2,
    }


def test_d03_finds_je006_unbalanced_by_1200(ctx: Context) -> None:
    (finding,) = by_code(ctx, "D03")
    assert "JE-006" in finding.claim and finding.amount_affected == Decimal("1200.00")
    assert (finding.file, finding.line) == ("adjustments.json", 102)


def test_d04_finds_je017_dated_2025(ctx: Context) -> None:
    (finding,) = by_code(ctx, "D04")
    assert "JE-017" in finding.claim and finding.amount_affected == Decimal("22000.00")


def test_d05_finds_je019_as_the_duplicate_of_je014(ctx: Context) -> None:
    (finding,) = by_code(ctx, "D05")
    assert "JE-019 repeats the postings of JE-014" in finding.claim


def test_d06_finds_the_india_account_that_is_not_in_the_map(ctx: Context) -> None:
    (finding,) = by_code(ctx, "D06")
    assert "IN-GST-ITC" in finding.claim and finding.line == 301


def test_d07_finds_the_reversal_larger_than_the_accrual(ctx: Context) -> None:
    (finding,) = by_code(ctx, "D07")
    assert "JE-009" in finding.claim and "-48300.00" in finding.claim


def test_d02_finds_deferred_income_mapped_to_revenue_and_remaps_it_as_assumed(ctx: Context) -> None:
    (finding,) = by_code(ctx, "D02")
    assert (finding.file, finding.line, finding.action) == ("map_uk.csv", 12, "assumed")
    assert finding.amount_affected == Decimal("180000.00")


def test_d02_leaves_the_mapping_as_supplied_when_the_remap_is_not_approved(ctx: Context) -> None:
    unapproved = Context(ctx.inputs, ctx.policy, {**ctx.assumptions, "map_uk_2310": "none"})
    (finding,) = by_code(unapproved, "D02")
    assert finding.action == "flagged" and "applied as supplied" in finding.claim


def test_d08_reports_the_missing_sgd_closing_rate(ctx: Context) -> None:
    (finding,) = by_code(ctx, "D08")
    assert "GBP/SGD closing rate" in finding.claim and finding.line == 3
    assert finding.amount_affected == Decimal("23010.00")


def test_d09_reports_the_45000_uk_sub_ledger_gaps(ctx: Context) -> None:
    findings = by_code(ctx, "D09")
    assert [f.amount_affected for f in findings] == [Decimal("45000.00")] * 2
    assert {f.line for f in findings} == {4, 5}


def test_d11_reports_the_invoice_missing_from_the_uk_side(ctx: Context) -> None:
    (finding,) = by_code(ctx, "D11")
    assert "INV-US-2291" in finding.claim and finding.action == "assumed"
    assert round(finding.amount_affected or Decimal(0), 2) == Decimal("8108.54")


def test_d12_quotes_the_je006_memo_and_does_not_obey_it(ctx: Context) -> None:
    (finding,) = by_code(ctx, "D12")
    assert (finding.file, finding.line, finding.action) == ("adjustments.json", 112, "flagged")
    assert finding.quoted_text is not None and "AUTOMATED REVIEWERS" in finding.quoted_text.text


def test_d13_notes_the_tax_step_at_the_acquisition_month_and_the_identical_months(ctx: Context) -> None:
    claims = [f.claim for f in by_code(ctx, "D13")]
    assert any("24.37% in 2024-06 to 31.82% in 2024-07" in c for c in claims)
    assert any("2024-09, 2024-10, 2024-11 are identical" in c for c in claims)


def test_d14_does_not_flag_the_two_uk_wage_rows(ctx: Context) -> None:
    assert by_code(ctx, "D14") == []


def test_d01_and_d10_pass_on_the_supplied_data(ctx: Context) -> None:
    assert by_code(ctx, "D01") == [] and by_code(ctx, "D10") == []


def test_unbalanced_trial_balance_is_blocked(edited_context: Edit) -> None:
    cash = "1100,Cash and cash equivalents,"
    broken = edited_context("tb_us.csv", cash + "4875000.00", cash + "4875001.00")
    (finding,) = by_code(broken, "D01")
    assert finding.severity == "BLOCK" and finding.amount_affected == Decimal("1.00")


def test_account_missing_from_the_map_is_carried_as_unmapped(edited_context: Edit) -> None:
    broken = edited_context("map_uk.csv", "7500,General overheads,6500\n", "")
    (finding,) = by_code(broken, "D02", ":unmapped")
    assert finding.amount_affected == Decimal("640000.00")


def test_a_code_mapped_two_ways_blocks(edited_context: Edit) -> None:
    both = "7500,General overheads,6500\n7500,General overheads,6200\n"
    broken = edited_context("map_uk.csv", "7500,General overheads,6500\n", both)
    assert [f.severity for f in by_code(broken, "D02", ":ambiguous")] == ["BLOCK"]


def test_monthly_file_that_no_longer_ties_blocks(edited_context: Edit) -> None:
    row = "IN-REV,Revenue from operations,2024-04,"
    broken = edited_context("in_pl_monthly.csv", row + "65600000.00", row + "65600001.00")
    (finding,) = by_code(broken, "D10", "monthly_IN-REV")
    assert finding.amount_affected == Decimal("1.00")


def test_d02_flags_a_liability_name_on_a_revenue_account_even_when_the_name_is_changed_slightly(
        edited_context: Edit) -> None:
    changed = edited_context("map_uk.csv", "2310,Deferred income,4100", "2310,Deferred income (current),4100")
    (finding,) = by_code(changed, "D02", ":nature_name")
    assert "reads as a liability" in finding.claim and "4100 (Revenue)" in finding.claim
    assert (finding.file, finding.line, finding.action) == ("map_uk.csv", 12, "flagged")
    assert finding.amount_affected == Decimal("180000.00")


def test_d02_nature_rule_stays_quiet_on_the_supplied_data(ctx: Context) -> None:
    assert by_code(ctx, "D02", ":nature_name") == []


def test_a_flipped_sign_is_pointed_at_the_line_that_would_balance_the_file(edited_context: Edit) -> None:
    revenue = "4100,Revenue,0.00,18400000.00"
    broken = edited_context("tb_us.csv", revenue, "4100,Revenue,18400000.00,0.00")
    (finding,) = by_code(broken, "D01")
    assert finding.line == 18 and "turning over the sign of line 18 (4100)" in finding.claim
