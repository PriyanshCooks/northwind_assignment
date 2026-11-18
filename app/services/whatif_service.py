"""Re-run on a patched copy of the inputs and diff the figures. The supplied files are never written."""
import csv
import io
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from app.domain.figures import Unknown
from app.services.run_service import Consolidation, build_context, stage
from app.utils.money import round2
from app.utils.paths import CONFIG_DIR

PATCH = re.compile(r"^(?P<file>[^:]+):(?P<line>\d+)\.(?P<column>\w+)=(?P<value>.*)$")


@dataclass
class Change:
    """Patches are 'file:LINE.column=value' (LINE counts the header as 1), appends add a CSV row, sets override an
    assumption for this run only."""

    patches: list[str] = field(default_factory=list)
    appends: list[str] = field(default_factory=list)
    sets: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Diff:
    figures: dict[str, tuple[str, str]]
    accounts: dict[str, tuple[Decimal, Decimal]]
    new_findings: tuple[str, ...] = ()
    cleared_findings: tuple[str, ...] = ()


def _lines(path: Path) -> list[str]:
    return path.read_bytes().decode("utf-8").splitlines(keepends=True)


def _ending(line: str) -> str:
    return line[len(line.rstrip("\r\n")):]


def _patch_cell(lines: list[str], header: list[str], line: int, column: str, value: str) -> None:
    if column not in header:
        raise ValueError(f"no column {column!r}; columns are {header}")
    cells = next(csv.reader([lines[line - 1].rstrip("\r\n")]))
    cells[header.index(column)] = value
    out = io.StringIO()
    csv.writer(out, lineterminator="").writerow(cells)
    lines[line - 1] = out.getvalue() + _ending(lines[line - 1])


def patched_copy(data_dir: Path, dest: Path, change: Change) -> None:
    shutil.copytree(data_dir, dest, dirs_exist_ok=True)
    for text in change.patches:
        match = PATCH.match(text)
        if not match:
            raise ValueError(f"patch {text!r} is not file:LINE.column=value")
        path = dest / match["file"]
        lines = _lines(path)
        header = next(csv.reader([lines[0].rstrip("\r\n")]))
        _patch_cell(lines, header, int(match["line"]), match["column"], match["value"])
        path.write_bytes("".join(lines).encode("utf-8"))
    for text in change.appends:
        name, _, row = text.partition("=")
        path = dest / name
        lines = _lines(path)
        newline = _ending(lines[0]) or "\n"
        body = "".join(lines)
        body += ("" if _ending(lines[-1]) else newline) + row + newline
        path.write_bytes(body.encode("utf-8"))


def _assumption(value: str) -> bool | str:
    return {"true": True, "false": False}.get(value.lower(), value)


def _run(data_dir: Path, config_dir: Path, sets: list[str]) -> Consolidation:
    ctx = build_context(data_dir, config_dir)
    for text in sets:
        key, _, value = text.partition("=")
        ctx.assumptions[key] = _assumption(value)
    return stage(ctx)


def shown(run: Consolidation) -> dict[str, str]:
    """Every control figure as text: 2 decimals, or 'null (reason)'."""
    out = {}
    for key, figure in run.figures.items():
        out[key] = f"null ({figure.reason})" if isinstance(figure, Unknown) else str(
            {k: v for k, v in figure.value.items()} if isinstance(figure.value, dict) else round2(figure.value))
    return out


def compare(before: Consolidation, after: Consolidation) -> Diff:
    old, new = shown(before), shown(after)
    figures = {k: (old[k], new[k]) for k in old if old[k] != new[k]}
    accounts = {a: (before.balances.get(a, Decimal(0)), after.balances.get(a, Decimal(0)))
                for a in sorted(set(before.balances) | set(after.balances))
                if round2(before.balances.get(a, Decimal(0))) != round2(after.balances.get(a, Decimal(0)))}
    was, now = {f.key for f in before.findings}, {f.key for f in after.findings}
    return Diff(figures, accounts, tuple(sorted(now - was)), tuple(sorted(was - now)))


def whatif(data_dir: Path, change: Change, config_dir: Path = CONFIG_DIR) -> Diff:
    with tempfile.TemporaryDirectory(prefix="northwind_whatif_") as tmp:
        patched = Path(tmp) / "data"
        patched_copy(data_dir, patched, change)
        return compare(_run(data_dir, config_dir, []), _run(patched, config_dir, change.sets))


def _nudge(text: str) -> str:
    """The same number 1% larger, with the same decimals (or +1 when it is zero)."""
    value = Decimal(text)
    places = max(-value.as_tuple().exponent, 0)  # type: ignore[operator]
    bumped = value * Decimal("1.01") if value else Decimal(1)
    return f"{bumped:.{places}f}"


def impact(data_dir: Path, target: str, config_dir: Path = CONFIG_DIR) -> Diff:
    """Which figures does 'file:LINE' feed? Nudge the row's rightmost number by 1% and see what moves."""
    name, _, line = target.partition(":")
    lines = _lines(data_dir / name)
    header = next(csv.reader([lines[0].rstrip("\r\n")]))
    cells = next(csv.reader([lines[int(line) - 1].rstrip("\r\n")]))
    for column, cell in reversed(list(zip(header, cells, strict=True))):
        if re.fullmatch(r"-?\d+(\.\d+)?", cell.strip()):
            return whatif(data_dir, Change(patches=[f"{name}:{line}.{column}={_nudge(cell.strip())}"]), config_dir)
    raise ValueError(f"{target} has no numeric cell to nudge")


def diff_inputs(baseline: Path, current: Path) -> list[str]:
    """What changed between two input folders: whole files by name, then the changed rows by line number."""
    out = []
    for path in sorted(current.iterdir()):
        old = baseline / path.name
        if not old.exists():
            out.append(f"{path.name}: new file")
        elif old.read_bytes() != path.read_bytes():
            before, after = _lines(old), _lines(path)
            changed = [i + 1 for i in range(max(len(before), len(after)))
                       if (before[i] if i < len(before) else None) != (after[i] if i < len(after) else None)]
            out.append(f"{path.name}: changed at line(s) {', '.join(map(str, changed))}")
    out += [f"{p.name}: removed" for p in sorted(baseline.iterdir()) if not (current / p.name).exists()]
    return out
