from datetime import date
from decimal import Decimal

import pytest

from app.core.post_journals import import_postings
from app.core.translate import ConsolidationBlocked, translate
from app.detectors.mapping import classified
from app.domain.entries import Posting
from app.domain.refs import make_ref
from app.domain.runs import Context
from app.parsers.fx_rates import FxTable
from app.parsers.mappings import apply_mapping
from app.utils.money import round2
from tests.conftest import Edit

YEAR_END = date(2024, 12, 31)


def translated(ctx: Context) -> list[Posting]:
    postings = import_postings(apply_mapping(classified(ctx), ctx.assumptions))
    return translate(postings, ctx.inputs, FxTable(ctx.inputs.rates), YEAR_END)


def line(rows: list[Posting], entity: str, account: str) -> Posting:
    return next(p for p in rows if p.entity == entity and p.account == account)


def test_us_cash_is_translated_at_the_closing_rate(ctx: Context) -> None:
    cash = line(translated(ctx), "US", "1100")
    assert round2(cash.amount) == Decimal("3890662.41")
    assert cash.rate_ref == "closing fx_rates.csv:6" and cash.ccy == "GBP"


def test_us_revenue_uses_the_fy_average_rate(ctx: Context) -> None:
    revenue = line(translated(ctx), "US", "4100")
    assert round2(revenue.amount) == round2(Decimal("-18400000.00") / Decimal("1.2780"))
    assert revenue.rate_ref == "average fx_rates.csv:3"


def test_uk_balances_are_not_changed_because_gbp_is_its_currency(ctx: Context) -> None:
    barclays = next(p for p in translated(ctx) if p.entity == "UK" and p.note.startswith("1200"))
    assert barclays.amount == Decimal("1240000.00") and barclays.rate_ref == "GBP functional"


def test_india_balance_sheet_is_translated_at_the_product_closing_rate(ctx: Context) -> None:
    bank = line(translated(ctx), "IN", "1100")
    assert bank.amount == Decimal("285000000.00") / Decimal("107.281860")
    assert bank.rate_ref == "closing fx_rates.csv:6 x fx_rates.csv:11"


def test_equity_lines_are_not_translated_into_the_consolidated_lines(ctx: Context) -> None:
    assert all(p.account not in {"3100", "3200", "3300", "3400"} for p in translated(ctx))


def test_translation_keeps_the_source_rows_and_the_origin(ctx: Context) -> None:
    cash = line(translated(ctx), "US", "1100")
    assert cash.origin == "IMPORT" and str(cash.sources[0]) == "tb_us.csv:2"


def test_a_missing_closing_rate_blocks_translation_instead_of_guessing(edited_context: Edit) -> None:
    ctx = edited_context("fx_rates.csv", "GBP,USD,closing,1.2530,2024-12-31,USD per 1 GBP\n", "")
    ref = make_ref("tb_us.csv", 2, "x")
    posting = Posting(entity="US", account="1100", amount="1.00", ccy="USD", origin="IMPORT", sources=(ref,))
    with pytest.raises(ConsolidationBlocked, match="no USD closing rate"):
        translate([posting], ctx.inputs, FxTable(ctx.inputs.rates), YEAR_END)
