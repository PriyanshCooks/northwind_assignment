import json

from app.agents.review.units import journal_units, mapping_units
from app.domain.runs import Context


def packets(ctx: Context) -> dict[str, dict]:  # type: ignore[type-arg]
    return {u.unit_id: u.packet for u in journal_units(ctx)}


def test_there_is_one_unit_per_journal_and_one_per_mapped_trial_balance_line(ctx: Context) -> None:
    assert len(journal_units(ctx)) == 20 and len(mapping_units(ctx)) == 43


def test_the_unbalanced_journal_packet_carries_both_totals(ctx: Context) -> None:
    packet = packets(ctx)["JE-006"]
    assert (packet["total_debit"], packet["total_credit"]) == ("51200.00", "50000.00")


def test_the_duplicate_pair_points_at_each_other(ctx: Context) -> None:
    found = packets(ctx)
    assert found["JE-014"]["same_lines_as"] == ["JE-019"] and found["JE-019"]["same_lines_as"] == ["JE-014"]


def test_the_period_and_the_unknown_account_are_in_the_packet(ctx: Context) -> None:
    found = packets(ctx)
    assert found["JE-017"]["date"] == "2025-01-06" and found["JE-017"]["period"] == ["2024-01-01", "2024-12-31"]
    assert [x["account"] for x in found["JE-016"]["lines"] if not x["in_entity_chart"]] == ["IN-GST-ITC"]


def test_a_reversal_that_flips_a_credit_balance_shows_before_and_after(ctx: Context) -> None:
    line = packets(ctx)["JE-009"]["lines"][0]
    seen = (line["balance_before"], line["balance_after"], line["normal_balance"])
    assert seen == ("-48300.00", "15700.00", "Credit")


def test_free_text_goes_into_a_packet_only_as_a_quoted_string(ctx: Context) -> None:
    description = packets(ctx)["JE-006"]["description"]
    assert description.startswith('"') and json.loads(description)


def test_a_mapping_packet_does_not_carry_any_detector_verdict(ctx: Context) -> None:
    unit = next(u for u in mapping_units(ctx) if u.packet["local_code"] == "2310")
    assert unit.packet["mapped_to"]["code"] == "4100" and "verdict" not in json.dumps(unit.packet)
