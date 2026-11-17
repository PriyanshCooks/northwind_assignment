
from decimal import Decimal

from app.domain.ledger import MappedLine
from app.domain.runs import Context
from app.parsers.mappings import apply_mapping, classify_all
from tests.conftest import Edit


def uk_line(mapped: list[MappedLine], code: str) -> MappedLine:
    return next(m for m in mapped if m.line.entity == "UK" and m.line.local_code == code)


def mapped_lines(ctx: Context, assumptions: dict[str, bool | str] | None = None) -> list[MappedLine]:
    raw = classify_all(ctx.inputs.trial_balances, ctx.inputs.maps, ctx.inputs.coa)
    return apply_mapping(raw, ctx.assumptions if assumptions is None else assumptions)


def uk_revenue(mapped: list[MappedLine]) -> Decimal:
    return -sum((m.line.amount for m in mapped if m.line.entity == "UK" and m.group_code == "4100"), Decimal(0))


def test_uk_deferred_income_is_remapped_to_2300_when_the_assumption_is_set(ctx: Context) -> None:
    item = uk_line(mapped_lines(ctx), "2310")
    assert (item.group_code, item.verdict) == ("2300", "REMAPPED")


def test_remap_takes_180000_out_of_uk_revenue(ctx: Context) -> None:
    approved = uk_revenue(mapped_lines(ctx))
    as_supplied = uk_revenue(mapped_lines(ctx, {}))
    assert (approved, as_supplied) == (Decimal("9850000.00"), Decimal("10030000.00"))


def test_without_the_assumption_the_mapping_stays_as_supplied_and_suspect(ctx: Context) -> None:
    item = uk_line(mapped_lines(ctx, {}), "2310")
    assert (item.group_code, item.verdict, item.proposed_group_code) == ("4100", "SUSPECT", "2300")


def test_us_codes_are_their_own_group_codes(ctx: Context) -> None:
    us = [m for m in mapped_lines(ctx) if m.line.entity == "US"]
    assert all(m.group_code == m.line.local_code and m.verdict == "OK" for m in us)


def test_a_deleted_map_row_gives_unmapped_and_the_total_is_preserved(edited_context: Edit) -> None:
    broken = edited_context("map_uk.csv", "7500,General overheads,6500\n", "")
    mapped = mapped_lines(broken)
    overheads = uk_line(mapped, "7500")
    assert (overheads.group_code, overheads.verdict) == (None, "UNMAPPED")
    assert sum((m.line.amount for m in mapped if m.line.entity == "UK"), Decimal(0)) == 0


def test_a_code_with_two_targets_is_ambiguous_and_never_takes_the_first_row(edited_context: Edit) -> None:
    both = "7500,General overheads,6500\n7500,General overheads,6200\n"
    mapped = mapped_lines(edited_context("map_uk.csv", "7500,General overheads,6500\n", both))
    assert (uk_line(mapped, "7500").group_code, uk_line(mapped, "7500").verdict) == (None, "AMBIGUOUS")


def test_a_map_row_pointing_at_a_missing_group_account_is_unmapped(edited_context: Edit) -> None:
    mapped = mapped_lines(edited_context("map_uk.csv", "7500,General overheads,6500", "7500,General overheads,9999"))
    assert uk_line(mapped, "7500").verdict == "UNMAPPED"
