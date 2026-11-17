from decimal import Decimal

from app.domain.entries import Entry
from app.domain.runs import Context
from app.services.run_service import Consolidation, stage
from app.utils.money import round2
from tests.conftest import Edit


def entry(run: Consolidation, entry_id: str) -> Entry:
    return next(e for e in run.eliminations if e.id == entry_id)


def amounts(e: Entry) -> dict[str, Decimal]:
    return {p.account: round2(p.amount) for p in e.lines}


def test_goodwill_is_147_6m_inr_or_1375815_07_gbp_at_closing(ctx: Context) -> None:
    acq = stage(ctx).acquisition
    assert acq is not None
    assert acq.goodwill_inr == Decimal("147600000")
    assert round2(acq.goodwill_gbp) == Decimal("1375815.07")


def test_nci_at_acquisition_is_20_percent_of_678m_inr_at_the_spot_rate(ctx: Context) -> None:
    acq = stage(ctx).acquisition
    assert acq is not None and round2(acq.nci_at_acquisition) == Decimal("1285958.29")


def test_nci_closing_is_1325107_53(ctx: Context) -> None:
    acq = stage(ctx).acquisition
    assert acq is not None and round2(acq.nci_closing) == Decimal("1325107.53")


def test_nci_profit_is_20_percent_of_the_post_acquisition_profit(ctx: Context) -> None:
    acq = stage(ctx).acquisition
    assert acq is not None and round2(acq.nci_profit) == Decimal("60858.06")
    assert round2(acq.nci_translation) == Decimal("-21708.82")


def test_india_pre_acquisition_profit_goes_to_reserves_and_its_books_still_balance(ctx: Context) -> None:
    local = stage(ctx).local
    india = [p for p in local if p.entity == "IN"]
    assert sum((p.amount for p in india), Decimal(0)) == 0
    carried = next(p for p in india if p.origin == "ACQUISITION")
    assert (carried.account, carried.amount) == ("3200", Decimal("-18000000.00"))


def test_india_income_statement_covers_only_july_to_december(ctx: Context) -> None:
    run = stage(ctx)
    income = [p for p in run.local if p.entity == "IN" and run.ctx.inputs.coa[p.account].statement == "PL"]
    profit_inr = -sum((p.amount for p in income), Decimal(0))
    assert profit_inr == Decimal("32800000.00")  # 42,000,000 before the six India journals


def test_intercompany_balances_eliminate_exactly(ctx: Context) -> None:
    e = entry(stage(ctx), "ELIM-IC-BALANCES")
    assert amounts(e) == {"2150": Decimal("510774.14"), "1250": Decimal("-510774.14")}
    assert e.is_balanced()


def test_intercompany_income_and_expense_eliminate_with_the_rate_residual_to_7300(ctx: Context) -> None:
    e = entry(stage(ctx), "ELIM-IC-INCOME")
    assert amounts(e) == {"4200": Decimal("500782.47"), "6300": Decimal("-498816.26"), "7300": Decimal("-1966.21")}
    assert e.is_balanced()


def test_both_investment_eliminations_balance_and_cite_their_sources(ctx: Context) -> None:
    run = stage(ctx)
    for entry_id in ("ELIM-INV-UK", "ELIM-INV-IN"):
        assert entry(run, entry_id).is_balanced()
    assert any(s.file == "acquisition_note.md" for p in entry(run, "ELIM-INV-IN").lines for s in p.sources)


def test_a_missing_inr_spot_rate_blocks_the_acquisition_not_the_whole_run(edited_context: Edit) -> None:
    ctx = edited_context("fx_rates.csv", "USD,INR,spot,83.39,2024-07-01,INR per 1 USD\n", "")
    run = stage(ctx)
    assert run.blocked is not None and "spot" in run.blocked
    assert run.findings  # detectors still ran
