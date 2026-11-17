"""Read a finished run's output files for the UI, compare two runs, and zip the chosen files. Nothing is recomputed:
the figures are the ones in control_figures_pb.json and control_figures_status.json."""
import io
import json
import re
import zipfile
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.services.registry_service import Registry
from app.services.run_service import OUTPUT_FILES
from app.services.whatif_service import diff_inputs, impact

ALWAYS = "run_manifest.json"
CHANGED = re.compile(r"^(?P<file>[^:]+): changed at line\(s\) (?P<lines>.+)$")
MAX_IMPACT_TARGETS = 10


def _two_places(text: str) -> str:
    return str(Decimal(text).quantize(Decimal("0.01")))


def _json(path: Path) -> Any:
    """Every non-integer number in an output file is money, sent on as text with two decimals so no float ever reaches
    the page. Counts such as the journal tallies are integers and stay integers."""
    return json.loads(path.read_text(encoding="utf-8"), parse_float=_two_places)


def figures(out_dir: Path) -> list[dict[str, Any]]:
    """The 12 figures with their status. A null carries the reason it is null (or the open items it rests on)."""
    values = _json(out_dir / "control_figures_pb.json")
    status = _json(out_dir / "control_figures_status.json")["figures"]
    return [{"key": key, "value": value, **status.get(key, {})} for key, value in values.items()]


def issues(out_dir: Path) -> list[dict[str, Any]]:
    return list(_json(out_dir / "issues.json")["issues"])


def available_outputs(out_dir: Path) -> list[dict[str, Any]]:
    names = [*OUTPUT_FILES, ALWAYS]
    return [{"name": n, "bytes": (out_dir / n).stat().st_size, "required": n == ALWAYS}
            for n in names if (out_dir / n).is_file()]


def build_zip(out_dir: Path, chosen: list[str]) -> bytes:
    """The chosen files plus the run manifest, which is always included. Only names that exist in the run's output
    folder are accepted, so a request cannot reach any other file."""
    allowed = {o["name"] for o in available_outputs(out_dir)}
    unknown = sorted(set(chosen) - allowed)
    if unknown:
        raise ValueError("not an output of this run: " + ", ".join(unknown))
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in sorted({*chosen, ALWAYS} & allowed):
            archive.write(out_dir / name, name)
    return buffer.getvalue()


def _targets(changes: list[str]) -> list[str]:
    found = []
    for text in changes:
        match = CHANGED.match(text)
        if match and match["file"].endswith(".csv"):
            found += [f"{match['file']}:{n.strip()}" for n in match["lines"].split(",") if n.strip().isdigit()]
    return found[:MAX_IMPACT_TARGETS]


def compare(registry: Registry, run_id: str, other_id: str) -> dict[str, Any]:
    """This run against another: which input lines differ, what each changed CSV line feeds (measured by nudging it
    1%), and the figures side by side."""
    data, baseline = registry.data_dir(run_id), registry.data_dir(other_id)
    changes = diff_inputs(baseline, data)
    measured = {}
    for target in _targets(changes):
        try:
            diff = impact(data, target, registry.config_dir(run_id))
            measured[target] = {k: {"before": a, "after": b} for k, (a, b) in diff.figures.items()}
        except (ValueError, IndexError, KeyError):
            measured[target] = {}
    before, after = figures(registry.out_dir(other_id)), figures(registry.out_dir(run_id))
    moved = [{"key": a["key"], "other": b["value"], "this": a["value"]}
             for a, b in zip(after, before, strict=True) if a["value"] != b["value"]]
    return {"input_changes": changes, "impact": measured, "figures": moved}
