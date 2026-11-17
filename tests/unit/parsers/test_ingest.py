from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.parsers.acquisition_note import load_acquisition, table_foots
from app.parsers.contracts import ContractError
from app.parsers.entities import load_entities, load_intercompany, load_subledger
from app.parsers.fx_rates import FxTable, load_rates
from app.parsers.journals import load_journals
from app.parsers.mappings import load_coa, load_map
from app.parsers.tb_adapters import load_india_monthly, load_tb
from app.utils.paths import DEFAULT_DATA_DIR as DATA


def tb(entity: str, ccy: str, name: str):
    return load_tb(DATA / name, entity, ccy)


def test_each_trial_balance_balances_on_its_own() -> None:
    assert sum(line.amount for line in tb("US", "USD", "tb_us.csv")) == 0
    assert sum(line.amount for line in tb("UK", "GBP", "tb_uk.csv")) == 0
    assert sum(line.amount for line in tb("IN", "INR", "tb_in.csv")) == 0


def test_us_cash_row_keeps_its_file_and_line() -> None:
    cash = tb("US", "USD", "tb_us.csv")[0]
    assert (cash.local_code, cash.amount, str(cash.ref)) == ("1100", Decimal("4875000.00"), "tb_us.csv:2")


def test_uk_plant_code_keeps_its_leading_zero() -> None:
    codes = [line.local_code for line in tb("UK", "GBP", "tb_uk.csv")]
    assert "0031" in codes and "31" not in codes


def test_uk_sgd_bank_keeps_its_foreign_amount() -> None:
    bank = next(line for line in tb("UK", "GBP", "tb_uk.csv") if line.local_code == "1210")
    assert (bank.txn_ccy, bank.txn_amount, bank.amount) == ("SGD", Decimal("40000.00"), Decimal("23010.00"))


def test_uk_gbp_rows_have_no_foreign_currency_fields() -> None:
    barclays = tb("UK", "GBP", "tb_uk.csv")[0]
    assert barclays.txn_ccy is None and barclays.txn_amount is None


def test_two_uk_wage_rows_keep_their_cost_centres() -> None:
    wages = [line for line in tb("UK", "GBP", "tb_uk.csv") if line.local_code == "7000"]
    assert sorted(line.cost_centre or "" for line in wages) == ["CC-OPS", "CC-SALES"]


def test_india_credit_rows_become_negative() -> None:
    depreciation = next(line for line in tb("IN", "INR", "tb_in.csv") if line.local_code == "IN-ACD")
    assert depreciation.amount == Decimal("-141000000.00")


def test_india_monthly_file_has_nine_months_of_eight_ledgers() -> None:
    assert len(load_india_monthly(DATA / "in_pl_monthly.csv")) == 72


def test_unknown_trial_balance_header_blocks(tmp_path: Path) -> None:
    bad = tmp_path / "tb_x.csv"
    bad.write_text("code,amount\n1,2\n", encoding="utf-8")
    with pytest.raises(ContractError, match="unknown trial balance layout"):
        load_tb(bad, "X", "GBP")


def test_non_numeric_amount_blocks_with_its_line(tmp_path: Path) -> None:
    bad = tmp_path / "tb_us.csv"
    rows = "account_code,account_name,debit,credit\n1100,Cash,4875000.00,0.00\n1200,AR,12x,0.00\n"
    bad.write_text(rows, encoding="utf-8")
    with pytest.raises(ContractError) as caught:
        load_tb(bad, "US", "USD")
    assert caught.value.line == 3


def test_dr_cr_label_outside_the_allowed_values_blocks(tmp_path: Path) -> None:
    bad = tmp_path / "tb_in.csv"
    bad.write_text("ledger_code,ledger_name,period,amount,dr_cr\nIN-AR,Debtors,FY25 YTD,5.00,Debit\n", encoding="utf-8")
    with pytest.raises(ContractError, match="dr_cr"):
        load_tb(bad, "IN", "INR")


def test_gbp_inr_closing_is_the_product_of_the_two_given_rates() -> None:
    fx = FxTable(load_rates(DATA / "fx_rates.csv"))
    assert fx.units_per_gbp("INR", "closing") == Decimal("107.281860")
    assert fx.ref("INR", "closing") == "closing fx_rates.csv:6 x fx_rates.csv:11"


def test_missing_sgd_closing_rate_is_none_not_a_guess() -> None:
    fx = FxTable(load_rates(DATA / "fx_rates.csv"))
    assert fx.units_per_gbp("SGD", "closing") is None
    assert fx.units_per_gbp("SGD", "opening") == Decimal("1.6830")


def test_india_average_is_the_h2_rate_because_of_its_acquisition_date() -> None:
    fx = FxTable(load_rates(DATA / "fx_rates.csv"))
    assert fx.average_type(date(2024, 7, 1), date(2024, 12, 31)) == "h2_average"
    assert fx.average_type(date(2016, 3, 1), date(2024, 12, 31)) == "average"


def test_a_reversed_convention_is_inverted(tmp_path: Path) -> None:
    path = tmp_path / "fx_rates.csv"
    path.write_text(
        "base_currency,quote_currency,rate_type,rate,as_of,convention\nGBP,USD,closing,0.8,2024-12-31,GBP per 1 USD\n",
        encoding="utf-8",
    )
    assert load_rates(path)[0].value == Decimal("1.25")


def test_unknown_rate_convention_blocks(tmp_path: Path) -> None:
    path = tmp_path / "fx_rates.csv"
    path.write_text(
        "base_currency,quote_currency,rate_type,rate,as_of,convention\nGBP,USD,closing,1.25,2024-12-31,USD/GBP\n",
        encoding="utf-8",
    )
    with pytest.raises(ContractError, match="convention"):
        load_rates(path)


def test_twenty_journals_load_with_the_memo_on_line_112() -> None:
    journals = load_journals(DATA / "adjustments.json")
    je6 = next(j for j in journals if j.id == "JE-006")
    assert len(journals) == 20
    assert str(je6.lines[0].memo_ref) == "adjustments.json:112"
    assert je6.total_debit() - je6.total_credit() == Decimal("1200.00")


def test_journal_account_codes_stay_text() -> None:
    je8 = next(j for j in load_journals(DATA / "adjustments.json") if j.id == "JE-008")
    assert je8.lines[1].account == "0031"


def test_acquisition_note_figures_and_footing() -> None:
    note = load_acquisition(DATA / "acquisition_note.md")
    assert (note.consideration_inr, note.net_assets_at_completion, note.interest_pct) == (
        Decimal("690000000"), Decimal("678000000"), Decimal("80"))
    assert note.completion_date == date(2024, 7, 1)
    assert table_foots(note)
    assert str(note.refs["consideration"]) == "acquisition_note.md:5"


def test_note_that_does_not_foot_is_detected() -> None:
    note = load_acquisition(DATA / "acquisition_note.md")
    assert not table_foots(note.model_copy(update={"net_assets_at_completion": Decimal("678000001")}))


def test_entities_supplied_data() -> None:
    entities = load_entities(DATA / "entities.csv")
    assert entities["IN"].ownership_pct == Decimal("80") and entities["IN"].acquisition_date == date(2024, 7, 1)
    assert entities["US"].ownership_pct is None


def test_intercompany_has_five_us_and_four_uk_invoices() -> None:
    invoices = load_intercompany(DATA / "intercompany.csv")
    assert [sum(1 for i in invoices if i.reporting_entity == e) for e in ("US", "UK")] == [5, 4]


def test_subledger_controls_and_mapping_files_load() -> None:
    assert len(load_subledger(DATA / "subledger_controls.csv")) == 6
    assert len(load_coa(DATA / "group_coa.csv")) == 31
    assert load_map(DATA / "map_uk.csv", "UK")["2310"][0].group_code == "4100"
