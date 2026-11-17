from decimal import Decimal

from app.core.intercompany import reconcile
from app.core.revalue import restated_amount, revalue
from app.detectors.mapping import classified
from app.domain.runs import Context
from app.parsers.fx_rates import FxTable
from app.parsers.mappings import apply_mapping
from app.utils.money import round2
from tests.conftest import Edit


def fx_of(ctx: Context) -> FxTable:
    return FxTable(ctx.inputs.rates)


def revaluation(ctx: Context):
    return revalue(apply_mapping(classified(ctx), ctx.assumptions), fx_of(ctx), "7300")


def test_uk_usd_payable_is_revalued_at_closing_with_a_loss_to_7300(ctx: Context) -> None:
    (entry,) = revaluation(ctx).entries
    amounts = {p.account: round2(p.amount) for p in entry.lines}
    assert amounts == {"2150": Decimal("-11957.88"), "7300": Decimal("11957.88")}
    assert entry.is_balanced()


def test_revaluation_entry_cites_the_trial_balance_line_and_the_rate_row(ctx: Context) -> None:
    (entry,) = revaluation(ctx).entries
    assert str(entry.lines[0].sources[0]) == "tb_uk.csv:10"
    assert entry.lines[0].rate_ref == "closing fx_rates.csv:6"


def test_sgd_bank_has_no_closing_rate_so_it_is_left_unresolved(ctx: Context) -> None:
    result = revaluation(ctx)
    assert [line.local_code for line in result.unresolved] == ["1210"]
    assert restated_amount(result.unresolved[0], fx_of(ctx)) is None


def test_adding_an_sgd_closing_rate_revalues_the_bank(edited_context: Edit) -> None:
    average = "GBP,SGD,average,1.7120,FY2024,SGD per 1 GBP"
    ctx = edited_context("fx_rates.csv", average, average + "\nGBP,SGD,closing,1.7000,2024-12-31,SGD per 1 GBP")
    result = revaluation(ctx)
    bank = next(e for e in result.entries if e.id == "REV-UK-1210")
    assert result.unresolved == []
    assert round2(bank.lines[0].amount) == Decimal("519.41")
    assert round2(23010 + bank.lines[0].amount) == Decimal("23529.41")


def test_intercompany_difference_is_20066_42(ctx: Context) -> None:
    result = reconcile(ctx.inputs, fx_of(ctx))
    assert result.difference is not None and round2(result.difference) == Decimal("20066.42")


def test_intercompany_causes_are_in_transit_plus_revaluation(ctx: Context) -> None:
    result = reconcile(ctx.inputs, fx_of(ctx))
    assert (round2(result.causes["in_transit"]), round2(result.causes["revaluation"])) == (
        Decimal("8108.54"), Decimal("11957.88"))
    assert abs(sum(result.causes.values(), Decimal(0)) - (result.difference or 0)) < Decimal("1e-30")


def test_only_inv_us_2291_is_in_transit_and_the_uk_records_it_at_closing(ctx: Context) -> None:
    result = reconcile(ctx.inputs, fx_of(ctx))
    (entry,) = result.entries
    assert [i.doc_ref for i in result.in_transit] == ["INV-US-2291"]
    legs = {p.account: round2(p.amount) for p in entry.lines}
    assert legs == {"6300": Decimal("8108.54"), "2150": Decimal("-8108.54")}
    assert entry.is_balanced() and entry.lines[0].entity == "UK"


def test_changing_the_closing_rate_changes_the_difference(edited_context: Edit) -> None:
    ctx = edited_context("fx_rates.csv", "GBP,USD,closing,1.2530", "GBP,USD,closing,1.2500")
    # 640,000 / 1.2500 = 512,000.00, less the 490,707.72 the UK booked
    assert round2(reconcile(ctx.inputs, fx_of(ctx)).difference or Decimal(0)) == Decimal("21292.28")


def test_missing_closing_rate_makes_the_difference_unknown(edited_context: Edit) -> None:
    ctx = edited_context("fx_rates.csv", "GBP,USD,closing,1.2530,2024-12-31,USD per 1 GBP\n", "")
    assert reconcile(ctx.inputs, fx_of(ctx)).difference is None
