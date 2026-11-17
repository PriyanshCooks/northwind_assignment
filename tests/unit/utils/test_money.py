from decimal import Decimal

import pytest

from app.utils.money import fmt2, round2, to_decimal


def test_float_is_refused() -> None:
    with pytest.raises(ValueError):
        to_decimal(1.2530)


def test_string_amount_keeps_every_digit() -> None:
    assert to_decimal("14069373.43") == Decimal("14069373.43")


def test_unreadable_text_is_refused() -> None:
    with pytest.raises(ValueError):
        to_decimal("12,5")


def test_half_cent_rounds_up() -> None:
    assert round2(Decimal("2.675")) == Decimal("2.68")


def test_us_cash_translated_at_closing_rate_rounds_to_the_golden_figure() -> None:
    assert fmt2(Decimal("4875000.00") / Decimal("1.2530")) == "3890662.41"


def test_intermediate_division_is_not_rounded() -> None:
    assert Decimal("10160") / Decimal("1.2530") != round2(Decimal("10160") / Decimal("1.2530"))
