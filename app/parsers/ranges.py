"""Dates that must fall in the financial year. Journal dates are not here: a journal outside the year is a finding
(JE-017 is rejected by the engine with a reason), not an unreadable file."""
from datetime import date, timedelta

from app.domain.runs import Inputs
from app.parsers.contracts import ContractError


def check_period(inputs: Inputs, start: date, end: date) -> None:
    """policy 1: the group year. India's monthly P&L, the invoices and the closing and opening rates sit in it."""
    for row in inputs.india_monthly:
        first = date.fromisoformat(row.month + "-01")
        if not start <= first <= end:
            raise ContractError(row.ref.file, row.ref.line, f"column month: {row.month} is outside {start} to {end}")
    for invoice in inputs.intercompany:
        if not start <= invoice.doc_date <= end:
            raise ContractError(
                invoice.ref.file, invoice.ref.line, f"column doc_date: {invoice.doc_date} is outside {start} to {end}",
            )
    expected = {"closing": end, "opening": start - timedelta(days=1)}
    for rate in inputs.rates:
        if rate.rate_type in expected and rate.as_of != expected[rate.rate_type].isoformat():
            raise ContractError(
                rate.ref.file, rate.ref.line,
                f"column as_of: a {rate.rate_type} rate is dated {expected[rate.rate_type]}, got {rate.as_of}",
            )
