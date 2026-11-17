"""Reads adjustments.json. Every journal and line keeps the line number it starts on in the file."""
import json
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.domain.journals import Journal, JournalLine
from app.domain.quarantine import Quarantined
from app.domain.refs import SourceRef, make_ref
from app.parsers.contracts import ContractError, split_lines


def _find_lines(lines: list[str], needle: str, start: int = 0) -> list[int]:
    return [i for i in range(start, len(lines)) if needle in lines[i]]


def _ref(name: str, lines: list[str], index: int) -> SourceRef:
    return make_ref(name, index + 1, lines[index].strip())


def _entry(name: str, lines: list[str], raw: dict[str, Any], start: int, stop: int) -> Journal:
    account_lines = [i for i in _find_lines(lines, '"account"', start) if i < stop]
    memo_lines = [i for i in _find_lines(lines, '"memo"', start) if i < stop]
    raw_lines = raw["lines"]
    if len(account_lines) != len(raw_lines):
        raise ContractError(name, start + 1, f"{raw['id']}: could not match its lines to the file")
    built = []
    for position, (index, item) in enumerate(zip(account_lines, raw_lines, strict=True)):
        next_account = account_lines[position + 1] if position + 1 < len(account_lines) else stop
        memo_at = next((m for m in memo_lines if index < m < next_account), None)
        has_memo = "memo" in item and memo_at is not None
        built.append(JournalLine(
            ref=_ref(name, lines, index), account=str(item["account"]), debit=item["debit"], credit=item["credit"],
            memo=Quarantined(text=item["memo"]) if has_memo else None,
            memo_ref=_ref(name, lines, memo_at) if has_memo and memo_at is not None else None,
        ))
    return Journal(
        ref=_ref(name, lines, start), id=raw["id"], entity=raw["entity"], date=date.fromisoformat(raw["date"]),
        description=Quarantined(text=raw["description"]), prepared_by=raw["prepared_by"], lines=tuple(built),
    )


def load_journals(path: Path) -> list[Journal]:
    lines = split_lines(path)
    try:
        # parse_float and parse_int keep every number as its text, so an amount is never a float
        document = json.loads("\n".join(lines), parse_float=str, parse_int=str)
        entries = document["entries"]
        starts = [_find_lines(lines, f'"id": "{e["id"]}"')[0] for e in entries]
    except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
        raise ContractError(path.name, 1, f"not a journal batch: {exc}") from exc
    stops = starts[1:] + [len(lines)]
    try:
        return [_entry(path.name, lines, e, start, stop) for e, start, stop in zip(entries, starts, stops, strict=True)]
    except (ValidationError, KeyError, ValueError) as exc:
        raise ContractError(path.name, 1, f"journal does not match its contract: {exc}") from exc
