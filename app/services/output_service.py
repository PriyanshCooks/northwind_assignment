"""Read a finished run's output files for the viewer: a list with metadata, one file as tables, the issues on it.
Money stays as the exact text in the file (JSON numbers are read as strings), so the page never sees a float."""
import csv
import io
import json
from pathlib import Path
from typing import Any

from app.services.results_service import available_outputs
from app.utils.hashing import sha256_file

MAX_BYTES = 2_000_000
MAX_ROWS = 500
STATEMENTS = {"balance_sheet.json", "profit_and_loss.json", "changes_in_equity.json"}


class TooLarge(ValueError):
    """The file is over the size cap for the in-page view; it can still be downloaded."""


def _path(out_dir: Path, name: str) -> Path:
    if name not in {o["name"] for o in available_outputs(out_dir)}:
        raise ValueError(f"not an output of this run: {name}")
    return out_dir / name


def _flat(value: Any, prefix: str = "") -> list[list[str]]:
    if isinstance(value, dict):
        return [row for k, v in value.items() for row in _flat(v, f"{prefix}{k}.")]
    if isinstance(value, list) and all(not isinstance(v, (dict, list)) for v in value):
        return [[prefix.rstrip("."), "\n".join(str(v) for v in value)]]
    return [[prefix.rstrip("."), "" if value is None else str(value)]]


def _sections(data: Any) -> list[dict[str, Any]]:
    """A JSON file as tables: a list of records is a table, anything else is key and value rows."""
    if isinstance(data, list) or not isinstance(data, dict):
        data = {"records": data}
    sections, plain = [], []
    for key, value in data.items():
        if isinstance(value, list) and value and all(isinstance(v, dict) for v in value):
            columns = list(dict.fromkeys(k for v in value for k in v))
            rows = [["" if v.get(c) is None else str(v.get(c)) for c in columns] for v in value]
            sections.append({"title": key, "columns": columns, "rows": rows})
        else:
            plain += _flat(value, f"{key}.")
    if plain:
        sections.insert(0, {"title": "Details", "columns": ["Field", "Value"], "rows": plain})
    return sections


def _parse(path: Path) -> list[dict[str, Any]]:
    if path.stat().st_size > MAX_BYTES:
        raise TooLarge(f"{path.name} is over {MAX_BYTES:,} bytes: download it instead")
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".csv":
        table = list(csv.reader(io.StringIO(text)))
        return [{"title": path.name, "columns": table[0], "rows": table[1:]}] if table else []
    return _sections(json.loads(text, parse_float=str, parse_int=str))


def file_list(out_dir: Path) -> list[dict[str, Any]]:
    rows = []
    for item in available_outputs(out_dir):
        path = out_dir / item["name"]
        try:
            count = sum(len(s["rows"]) for s in _parse(path))
        except TooLarge:
            count = None
        rows.append({"name": item["name"], "bytes": item["bytes"], "sha256": sha256_file(path), "rows": count})
    return rows


def file_view(out_dir: Path, name: str) -> dict[str, Any]:
    sections = _parse(_path(out_dir, name))
    total = sum(len(s["rows"]) for s in sections)
    left = MAX_ROWS
    for s in sections:
        s["rows"], left = s["rows"][:left], max(left - len(s["rows"]), 0)
    return {"name": name, "sections": sections, "total_rows": total, "truncated": total > MAX_ROWS,
            "sha256": sha256_file(out_dir / name), "bytes": (out_dir / name).stat().st_size}


def _read_csv(path: Path) -> tuple[list[str], list[list[str]]]:
    header, *rows = csv.reader(path.read_text(encoding="utf-8").splitlines())
    return header, rows


def _traced(out_dir: Path) -> dict[str, set[str]]:
    """For each output file, the input file:line references its rows come from (the source_rows columns). A statement
    is sourced from the consolidated accounts it lists."""
    refs: dict[str, set[str]] = {}
    by_account: dict[str, set[str]] = {}
    for name in ("consolidated_tb.csv", "eliminations.csv"):
        header, rows = _read_csv(out_dir / name)
        at = header.index("source_rows")
        refs[name] = {r.strip() for row in rows for r in row[at].split(";")}
        if name == "consolidated_tb.csv":
            by_account = {row[0]: {r.strip() for r in row[at].split(";")} for row in rows}
    for name in STATEMENTS & {o["name"] for o in available_outputs(out_dir)}:
        listed = {row[s["columns"].index("account")] for s in _parse(out_dir / name) if "account" in s["columns"]
                  for row in s["rows"]}
        refs[name] = set().union(*(by_account.get(a, set()) for a in listed))
    return refs


def issues_by_file(out_dir: Path, cards: list[dict[str, Any]], name: str) -> dict[str, list[dict[str, Any]]]:
    """Cards whose input file:line feeds this output (by its source rows), or that name a figure in this file. Cards
    that cannot be traced to this file are returned as run-wide: never guessed."""
    _path(out_dir, name)
    refs = _traced(out_dir).get(name, set())
    figures = set(json.loads((out_dir / "control_figures_pb.json").read_text(encoding="utf-8")))
    hit: list[dict[str, Any]] = []
    wide: list[dict[str, Any]] = []
    for card in cards:
        where = f"{card['evidence']['file']}:{card['evidence']['line']}"
        affects = (name == "issues.json" or where in refs
                   or (name.startswith("control_figures") and card["figure"] in figures))
        (hit if affects else wide).append(card)
    return {"affecting": hit, "run_wide": wide}
