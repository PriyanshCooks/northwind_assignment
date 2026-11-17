"""Decimal helpers. Floats are rejected; rounding happens only at output (assumption A13: half up)."""
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation, getcontext

# policy 7: translate at full precision. 50 digits keeps every intermediate exact for these magnitudes.
getcontext().prec = 50

CENT = Decimal("0.01")
ZERO = Decimal("0")


def to_decimal(value: object) -> Decimal:
    """Build a Decimal from a string, int or Decimal. A float is refused because it already carries binary error."""
    if isinstance(value, bool) or isinstance(value, float):
        raise ValueError("money is never a float: pass a string such as '1234.50'")
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, str):
        try:
            return Decimal(value.strip())
        except InvalidOperation as exc:
            raise ValueError(f"not a decimal number: {value!r}") from exc
    raise ValueError(f"cannot read {type(value).__name__} as money")


def round2(value: Decimal) -> Decimal:
    """Round a reported figure to 2 decimals. Called only when writing output (policy 7)."""
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def fmt2(value: Decimal) -> str:
    return format(round2(value), "f")
