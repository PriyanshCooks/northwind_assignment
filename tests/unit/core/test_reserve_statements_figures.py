from decimal import Decimal

from app.domain.figures import Determined, Provisional, Unknown
from app.domain.runs import Context
from app.services.run_service import Consolidation, stage
from app.utils.money import round2
from tests.conftest import Edit


def value(run: Consolidation, key: str) -> Decimal:
    figure = run.figures[key]
    assert isinstance(figure, (Determined, Provisional))
    assert isinstance(figure.value, Decimal)
    return round2(figure.value)


def test_reserve_movement_is_43706_74_by_the_balance_route(ctx: Context) -> None:
    run = stage(ctx)
    assert run.reserve is not None
    assert round2(run.reserve.movement_balance) == Decimal("43706.74")
    assert round2(run.reserve.closing) == Decimal("456056.74")


def test_the_two_reserve_routes_agree_within_one_cent(ctx: Context) -> None:
    run = stage(ctx)
    assert run.reserve is not None
    assert round2(run.reserve.movement_components) == Decimal("43706.74")
    assert abs(run.reserve.difference) < Decimal("0.01")


def test_reserve_components_each_come_from_a_named_exchange_difference(ctx: Context) -> None:
    parts = stage(ctx).reserve.components  # type: ignore[union-attr]
    assert {k: round2(v) for k, v in parts.items()} == {
        "us_opening_net_assets": Decimal("201488.13"), "us_profit": Decimal("28979.74"),
        "india_net_assets_and_profit_owners": Decimal("-86835.30"), "india_goodwill": Decimal("-23944.83"),
        "uk_investment_retranslation_removed": Decimal("-15924.08"),
        "india_investment_retranslation_removed": Decimal("-60056.92"),
    }


def test_twelve_figures_are_produced_under_the_brief_keys(ctx: Context) -> None:
    assert set(stage(ctx).figures) == {
        "group_revenue", "group_profit", "profit_owners", "profit_nci", "nci_closing", "goodwill_closing",
        "translation_reserve_movement", "total_assets", "total_equity", "intercompany_difference",
        "sgd_bank_gbp", "journals",
    }


def test_sgd_bank_is_unknown_with_a_reason_and_total_assets_is_provisional(ctx: Context) -> None:
    run = stage(ctx)
    sgd = run.figures["sgd_bank_gbp"]
    assert isinstance(sgd, Unknown) and "no GBP/SGD closing rate" in sgd.reason
    assets = run.figures["total_assets"]
    assert isinstance(assets, Provisional) and "carried at its booked 23010.00" in assets.open_items[0]


def test_figures_that_do_not_depend_on_the_sgd_item_stay_determined(ctx: Context) -> None:
    run = stage(ctx)
    for key in ("group_revenue", "profit_nci", "nci_closing", "goodwill_closing", "translation_reserve_movement"):
        assert isinstance(run.figures[key], Determined), key


def test_group_revenue_excludes_the_intercompany_fee(ctx: Context) -> None:
    assert value(stage(ctx), "group_revenue") == Decimal("28301607.81")


def test_balance_sheet_balances_and_equity_equals_net_assets(ctx: Context) -> None:
    sheet = stage(ctx).statements["balance_sheet"]
    assets, liabilities, equity = sheet["total_assets"], sheet["total_liabilities"], sheet["total_equity"]
    assert abs(assets - liabilities - equity) < Decimal("0.0001")  # type: ignore[operator]


def test_changes_in_equity_closes_to_total_equity(ctx: Context) -> None:
    run = stage(ctx)
    closing = run.statements["changes_in_equity"]["rows"][-1]["total"]  # type: ignore[index]
    assert abs(closing - run.statements["balance_sheet"]["total_equity"]) < Decimal("0.0001")  # type: ignore[operator]


def test_profit_and_loss_splits_between_owners_and_nci(ctx: Context) -> None:
    pl = stage(ctx).statements["profit_and_loss"]
    split = pl["attributable_to"]
    assert round2(split["owners_of_the_parent"]) == Decimal("2707922.89")  # type: ignore[index]
    assert round2(split["non_controlling_interest"]) == Decimal("60858.06")  # type: ignore[index]


def test_adding_the_sgd_rate_makes_the_figure_a_number_and_clears_the_marker(edited_context: Edit) -> None:
    average = "GBP,SGD,average,1.7120,FY2024,SGD per 1 GBP"
    run = stage(edited_context("fx_rates.csv", average, average + "\nGBP,SGD,closing,1.7000,2024-12-31,SGD per 1 GBP"))
    assert value(run, "sgd_bank_gbp") == Decimal("23529.41")
    assert isinstance(run.figures["total_assets"], Determined)


def test_a_missing_usd_closing_rate_blocks_the_run_and_every_figure_is_unknown(edited_context: Edit) -> None:
    run = stage(edited_context("fx_rates.csv", "GBP,USD,closing,1.2530,2024-12-31,USD per 1 GBP\n", ""))
    assert run.blocked is not None
    assert all(isinstance(f, Unknown) for f in run.figures.values())
