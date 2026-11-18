"""A date with a two-digit year is not proved wrong: code cannot tell which century was meant."""
from app.agents.reasoning.text_checks import invalid_date


def test_a_two_digit_year_is_not_called_invalid() -> None:
    assert invalid_date("Boy1 = 31.12.24", 2024) is False


def test_a_four_digit_impossible_date_still_is() -> None:
    assert invalid_date("236fev2 ed = 00.02.2222", 2024) is True
    assert invalid_date("Boy1 = 11.18.2026", 2026) is True
