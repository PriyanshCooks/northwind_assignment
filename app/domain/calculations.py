"""A calculation record: one output number as a formula, the inputs it was computed from, and the result."""
from typing import Literal

from app.domain.refs import Model, Money


class CalcInput(Model):
    """`source` is a file:line, or `calc:<id>` when the input is itself the result of another record."""

    name: str
    label: str
    value: Money
    source: str


class CalcRecord(Model):
    id: str
    kind: Literal["row", "figure"]
    label: str
    formula: str
    inputs: tuple[CalcInput, ...]
    result: Money
