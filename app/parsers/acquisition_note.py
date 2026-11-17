"""The acquisition note: pulls the figures out of its bullets and table, and checks that the table foots."""
import re
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from app.domain.refs import SourceRef, make_ref
from app.domain.runs import Acquisition
from app.parsers.contracts import ContractError, check_percentage, split_lines
from app.utils.money import to_decimal

PATTERNS = {
    "completion": r"\*\*Completion date:\*\*\s*(\d{1,2} \w+ \d{4})",
    "interest": r"\*\*Interest acquired:\*\*\s*(\d+(?:\.\d+)?)%",
    "consideration": r"\*\*Consideration:\*\*\s*INR ([\d,]+)",
    "share_capital": r"\|\s*Equity share capital\s*\|\s*([\d,]+)\s*\|",
    "reserves": r"\|\s*Reserves and surplus at .*?\|\s*([\d,]+)\s*\|",
    "profit": r"\|\s*Profit for .*?\|\s*([\d,]+)\s*\|",
    "net_assets": r"\|\s*\*\*Net assets at completion\*\*\s*\|\s*\*\*([\d,]+)\*\*\s*\|",
}


def _find(name: str, lines: list[str], key: str) -> tuple[str, SourceRef]:
    for index, text in enumerate(lines):
        match = re.search(PATTERNS[key], text)
        if match:
            return match.group(1), make_ref(name, index + 1, text.strip())
    raise ContractError(name, 1, f"acquisition note has no {key.replace('_', ' ')}")


def _amount(text: str) -> Decimal:
    return to_decimal(text.replace(",", ""))


def load_acquisition(path: Path) -> Acquisition:
    lines = split_lines(path)
    found = {key: _find(path.name, lines, key) for key in PATTERNS}
    interest = check_percentage(path.name, found["interest"][1].line, "interest acquired", found["interest"][0])
    completion = datetime.strptime(found["completion"][0], "%d %B %Y").date()
    return Acquisition(
        completion_date=completion,
        interest_pct=interest,
        consideration_inr=_amount(found["consideration"][0]),
        equity_share_capital=_amount(found["share_capital"][0]),
        reserves_at_start=_amount(found["reserves"][0]),
        profit_before_completion=_amount(found["profit"][0]),
        net_assets_at_completion=_amount(found["net_assets"][0]),
        refs={key: ref for key, (_, ref) in found.items()},
    )


def table_foots(note: Acquisition) -> bool:
    parts = note.equity_share_capital + note.reserves_at_start + note.profit_before_completion
    return parts == note.net_assets_at_completion
