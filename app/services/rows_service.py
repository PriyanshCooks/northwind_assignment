"""A source file as labelled rows. A row is one CSV record, one journal in adjustments.json, or one non-blank line of a
markdown file; its line number is the one the detectors cite, so a finding lands on the row it is about."""
import csv
import io
import json
import re
from bisect import bisect_right
from pathlib import Path
from typing import Any

JOURNAL_ID = re.compile(r'^\s*"id":\s*"([^"]+)"')


def _cell(label: str, value: object) -> dict[str, str]:
    return {"label": label, "value": "" if value is None else str(value)}


def _csv_rows(text: str) -> list[dict[str, Any]]:
    reader = csv.reader(io.StringIO(text))
    header = next(reader, [])
    rows = []
    for record in reader:
        if record:
            padded = record + [""] * (len(header) - len(record))
            rows.append({"line": reader.line_num, "cells": [_cell(h, v) for h, v in zip(header, padded, strict=False)]})
    return rows


def _postings(lines: list[dict[str, Any]]) -> str:
    """One posting per line, '6100 Dr 85000.00', amounts exactly as the file has them, with the posting's memo if it has
    one. The memo is shown as text and never acted on (JE-006's memo is a finding, not an instruction)."""
    parts = []
    for p in lines:
        side, amount = ("Dr", p.get("debit")) if p.get("debit") not in (None, "", "0.00") else ("Cr", p.get("credit"))
        memo = f' (memo: "{p["memo"]}")' if p.get("memo") else ""
        parts.append(f"{p.get('account')} {side} {amount}{memo}")
    return "\n".join(parts)


def _journal_rows(text: str) -> list[dict[str, Any]]:
    """One row per journal, at the line of its "id" (the line the journal findings cite)."""
    start = {m[1]: n for n, raw in enumerate(text.splitlines(), 1) if (m := JOURNAL_ID.match(raw))}
    entries = json.loads(text, parse_float=str, parse_int=str)["entries"]
    rows = []
    for entry in entries:
        cells = [_cell(k, v) for k, v in entry.items() if k != "lines"]
        cells.append(_cell("postings", _postings(entry.get("lines", []))))
        rows.append({"line": start[str(entry["id"])], "cells": cells})
    return sorted(rows, key=lambda r: int(r["line"]))


def _text_rows(text: str) -> list[dict[str, Any]]:
    return [{"line": n, "cells": [_cell("text", raw)]} for n, raw in enumerate(text.splitlines(), 1) if raw.strip()]


def read_rows(path: Path) -> list[dict[str, Any]]:
    """Rows in file order. The text is read as data and never interpreted."""
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".csv":
        return _csv_rows(text)
    if path.suffix == ".json":
        return _journal_rows(text)
    return _text_rows(text)


def row_for_line(rows: list[dict[str, Any]], line: int | None) -> int | None:
    """Index of the row a cited line belongs to: the last row starting at or before it. A line before the first row
    (a header) or no line at all belongs to no row."""
    if line is None or not rows:
        return None
    at = bisect_right([r["line"] for r in rows], line) - 1
    return at if at >= 0 else None
