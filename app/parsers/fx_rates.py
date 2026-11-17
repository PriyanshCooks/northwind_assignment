"""Rates, with direction parsed from the convention column. Nothing is assumed about which way a rate points."""
import re
from datetime import date
from decimal import Decimal
from pathlib import Path

from app.domain.runs import RateRow
from app.parsers.contracts import Contract, ContractError, finite_decimal, read_rows

FX = Contract(("base_currency", "quote_currency", "rate_type", "rate", "as_of", "convention"), decimals=("rate",))
CONVENTION = re.compile(r"^([A-Z]{3}) per 1 ([A-Z]{3})$")


def _check_rate(name: str, line: int, text: str) -> Decimal:
    """A missing, zero or negative rate would divide by zero or flip a sign, so it stops the run before any figure."""
    if not text:
        raise ContractError(name, line, "column rate: missing")
    rate = finite_decimal(name, line, "rate", text)
    if rate <= 0:
        raise ContractError(name, line, f"column rate: must be greater than zero, got {text}")
    return rate


def _no_repeats(name: str, rows: list[tuple[int, str, str, str, str, Decimal]]) -> None:
    """One rate per pair, type and date, in either direction: a second row is a duplicate or a conflict."""
    seen: dict[tuple[frozenset[str], str, str], tuple[int, Decimal]] = {}
    for line, base, quote, rate_type, as_of, rate in rows:
        key = (frozenset((base, quote)), rate_type, as_of)
        if key in seen:
            first_line, first_rate = seen[key]
            how = "repeats" if first_rate == rate else f"conflicts with ({first_rate} against {rate})"
            raise ContractError(name, line, f"{base}/{quote} {rate_type} {as_of} {how} line {first_line}")
        seen[key] = (line, rate)


def load_rates(path: Path) -> tuple[RateRow, ...]:
    rates: list[RateRow] = []
    seen: list[tuple[int, str, str, str, str, Decimal]] = []
    for row in read_rows(path, FX):
        v = row.values
        match = CONVENTION.match(v["convention"])
        if not match:
            raise ContractError(path.name, row.line, f"unknown rate convention {v['convention']!r}")
        units, per_one = match.groups()
        rate = _check_rate(path.name, row.line, v["rate"])
        base, quote = v["base_currency"], v["quote_currency"]
        if (units, per_one) == (quote, base):
            value = rate
        elif (units, per_one) == (base, quote):
            value = 1 / rate
        else:
            raise ContractError(path.name, row.line, f"convention {v['convention']!r} does not match {base}/{quote}")
        rates.append(
            RateRow(ref=row.ref, base=base, quote=quote, rate_type=v["rate_type"], value=value, as_of=v["as_of"])
        )
        seen.append((row.line, base, quote, v["rate_type"], v["as_of"], value))
    _no_repeats(path.name, seen)
    return tuple(rates)


class FxTable:
    """Every lookup answers in GBP terms and returns None when the file does not give the rate: never a guess."""

    def __init__(self, rates: tuple[RateRow, ...]) -> None:
        self._by = {(r.base, r.quote, r.rate_type): r for r in rates}
        self._rates = rates

    def _quote_per_gbp(self, ccy: str, rate_type: str) -> tuple[Decimal, list[str]] | None:
        direct = self._by.get(("GBP", ccy, rate_type))
        if direct:
            return direct.value, [str(direct.ref)]
        inverse = self._by.get((ccy, "GBP", rate_type))
        if inverse:
            return 1 / inverse.value, [str(inverse.ref)]
        first, second = self._by.get(("GBP", "USD", rate_type)), self._by.get(("USD", ccy, rate_type))
        if first and second:  # policy 2: product of the two given rates of the same type
            return first.value * second.value, [str(first.ref), str(second.ref)]
        return None

    def units_per_gbp(self, ccy: str, rate_type: str) -> Decimal | None:
        if ccy == "GBP":
            return Decimal(1)
        found = self._quote_per_gbp(ccy, rate_type)
        return None if found is None else found[0]

    def ref(self, ccy: str, rate_type: str) -> str:
        if ccy == "GBP":
            return "GBP functional"
        found = self._quote_per_gbp(ccy, rate_type)
        return f"{rate_type} {ccy}/GBP missing" if found is None else f"{rate_type} " + " x ".join(found[1])

    def to_gbp(self, amount: Decimal, ccy: str, rate_type: str) -> Decimal | None:
        rate = self.units_per_gbp(ccy, rate_type)
        return None if rate is None else amount / rate

    def average_type(self, acquired: date | None, year_end: date) -> str | None:
        """FY average for an entity held all year; the average for the period it was owned otherwise (policy 2)."""
        if acquired is None or acquired.year < year_end.year:
            return "average"
        window = f"{acquired.isoformat()} to {year_end.isoformat()}"
        match = [r.rate_type for r in self._rates if r.as_of == window and "average" in r.rate_type]
        return match[0] if match else None
