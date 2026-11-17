"""Schema contract per file: columns, types and allowed values. A violation blocks with file, line and reason."""
import csv
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path

from app.domain.refs import SourceRef, make_ref
from app.utils.money import to_decimal


class ContractError(Exception):
    """The input does not match its contract. Carries the place so the finding can say where."""

    def __init__(self, file: str, line: int, reason: str) -> None:
        super().__init__(f"{file}:{line}: {reason}")
        self.file = file
        self.line = line
        self.reason = reason


@dataclass(frozen=True)
class Contract:
    columns: tuple[str, ...]
    decimals: tuple[str, ...] = ()
    dates: tuple[str, ...] = ()
    allowed: dict[str, frozenset[str]] = field(default_factory=dict)


@dataclass(frozen=True)
class RawRow:
    line: int
    values: dict[str, str]
    ref: SourceRef


def split_lines(path: Path) -> list[str]:
    try:
        return path.read_bytes().decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise ContractError(path.name, 1, f"not valid UTF-8: {exc.reason}") from exc


def read_header(path: Path) -> tuple[str, ...]:
    lines = split_lines(path)
    if not lines:
        raise ContractError(path.name, 1, "file is empty")
    return tuple(next(csv.reader([lines[0]])))


def finite_decimal(name: str, line: int, column: str, value: object) -> Decimal:
    """An amount as a Decimal, or a ContractError naming the place. NaN and infinity parse, so they are refused."""
    try:
        number = to_decimal(value)
    except ValueError as exc:
        raise ContractError(name, line, f"column {column}: {exc}") from exc
    if not number.is_finite():
        raise ContractError(name, line, f"column {column}: {value!r} is not a finite number")
    return number


def check_percentage(name: str, line: int, column: str, text: str) -> Decimal:
    """A holding is above 0 and at most 100 percent: 0 is no holding, and 100 is the wholly owned UK."""
    value = finite_decimal(name, line, column, text)
    if not 0 < value <= 100:
        raise ContractError(name, line, f"column {column}: {text} is outside 0 to 100 percent")
    return value


def _check(name: str, line: int, values: dict[str, str], contract: Contract) -> None:
    for column in contract.decimals:
        if values[column]:
            finite_decimal(name, line, column, values[column])
    for column in contract.dates:
        try:
            date.fromisoformat(values[column])
        except ValueError as exc:
            raise ContractError(name, line, f"column {column}: not an ISO date: {values[column]!r}") from exc
    for column, options in contract.allowed.items():
        if values[column] not in options:
            raise ContractError(name, line, f"column {column}: {values[column]!r} is not one of {sorted(options)}")


def read_rows(path: Path, contract: Contract) -> list[RawRow]:
    """Read a CSV against its contract. Only outer whitespace is trimmed; codes stay text (0031 is not 31)."""
    lines = split_lines(path)
    header = read_header(path)
    if header != contract.columns:
        raise ContractError(path.name, 1, f"unexpected header {list(header)}; expected {list(contract.columns)}")
    rows: list[RawRow] = []
    for number, text in enumerate(lines[1:], start=2):
        if not text.strip():
            continue
        cells = next(csv.reader([text]))
        if len(cells) != len(header):
            raise ContractError(path.name, number, f"{len(cells)} fields, expected {len(header)}")
        values = {name: cell.strip() for name, cell in zip(header, cells, strict=True)}
        _check(path.name, number, values, contract)
        rows.append(RawRow(line=number, values=values, ref=make_ref(path.name, number, text)))
    return rows
