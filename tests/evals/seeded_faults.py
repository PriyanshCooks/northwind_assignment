"""Seeded-fault evaluation: plant six faults in a copy of the data, run the reasoning layer on the copy, and say for
each fault whether the layer hit it, missed it, and how many false alarms came with it. The faults are labelled by
construction (the changed lines are found by diffing the copy against the original), so no label depends on a model.
The layer sees the same packets as on clean data: no rule finding or verdict is put into any of them."""
import difflib
import json
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from app.llm.client import Mode
from app.llm.factory import LlmConfig, load_llm_config
from app.llm.ledger import Ledger
from app.reasoning.evidence import Evidence
from app.services.reasoning_service import ReasoningReport, build_evidence, run_reasoning
from app.services.run_service import Consolidation, build_context, stage
from app.utils.paths import CONFIG_DIR, DEFAULT_DATA_DIR, RUNTIME_DIR


@dataclass(frozen=True)
class Fault:
    name: str
    file: str
    old: str  # the exact text replaced (first match after `after`), or the whole line to duplicate
    new: str | None  # None means the line `old` is duplicated
    after: str = ""


FAULTS = (
    Fault("rate x100", "fx_rates.csv", "GBP,USD,closing,1.2530,", "GBP,USD,closing,125.30,"),
    Fault("journal amount typo", "adjustments.json", '"debit": "85000.00"', '"debit": "850000.00"', '"id": "JE-001"'),
    Fault("map Revenue to Tax", "map_uk.csv", "4000,Sales,4100", "4000,Sales,8100"),
    Fault("contradicting label", "tb_uk.csv", "1200,Bank - Barclays GBP,", "1200,Accruals,"),
    Fault("date typo", "adjustments.json", '"date": "2024-12-31"', '"date": "2042-12-31"', '"id": "JE-002"'),
    Fault("duplicated line", "intercompany.csv",
          "US,UK,INV-US-2201,2024-03-31,USD,157460.00,USD,157460.00,Management fee", None),
)


def _edit(text: str, fault: Fault) -> str:
    start = text.index(fault.after) if fault.after else 0
    at = text.index(fault.old, start)
    if fault.new is not None:
        return text[:at] + fault.new + text[at + len(fault.old):]
    end = text.index("\n", at) + 1
    return text[:end] + text[at:end] + text[end:]


def changed_lines(before: str, after: str) -> list[int]:
    """Line numbers, in `after`, of every line that is new or different."""
    a, b = before.splitlines(), after.splitlines()
    out: list[int] = []
    for tag, _, _, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag != "equal":
            out += range(j1 + 1, j2 + 1)
    return out


def plant(dst: Path, src: Path = DEFAULT_DATA_DIR) -> dict[str, set[str]]:
    """Copy the data to `dst`, plant every fault, and return fault name -> the file:line cites that changed."""
    shutil.copytree(src, dst)
    cites: dict[str, set[str]] = {}
    for fault in FAULTS:
        target = dst / fault.file
        before = target.read_bytes().decode("utf-8")
        newline = "\r\n" if "\r\n" in before else "\n"
        edited = _edit(before.replace(newline, "\n"), fault).replace("\n", newline)
        target.write_bytes(edited.encode("utf-8"))
        cites[fault.name] = {f"{fault.file}:{n}" for n in changed_lines(before, edited)}
    return cites


def _touched(evidence: Evidence, calc_id: str) -> set[str]:
    """The source lines a calculation record was built from."""
    return {row.split(": ", 1)[0] for row in evidence.lineage.get(calc_id, "").splitlines()}


def score(report: ReasoningReport, evidence: Evidence, cites: dict[str, set[str]]) -> dict[str, object]:
    """A fault is hit when a kept claim names one of its lines, or a kept calculation concern is built from one."""
    assert report.inputs is not None and report.calcs is not None
    by_reader = {f.cite for f in report.inputs.findings}
    by_calc = {c: _touched(evidence, c) for c in report.calcs.concerns()}
    every = set().union(*cites.values())
    faults = {}
    for name, lines in cites.items():
        via = "reader" if lines & by_reader else "calculation" if any(lines & t for t in by_calc.values()) else None
        faults[name] = {"result": "hit" if via else "miss", "via": via, "lines": sorted(lines)}
    false_alarms = sorted(by_reader - every) + sorted(c for c, t in by_calc.items() if not t & every)
    return {"faults": faults, "false_alarms": len(false_alarms), "false_alarm_cites": false_alarms,
            "hits": sum(f["result"] == "hit" for f in faults.values()), "dropped": len(report.inputs.dropped)}


def rules_caught(run: Consolidation, cites: dict[str, set[str]]) -> dict[str, list[str]]:
    """The comparison the layer is judged against: fault -> the rule findings that point at one of its lines."""
    at: dict[str, list[str]] = {}
    for f in run.findings:
        if f.line:
            at.setdefault(f"{f.file}:{f.line}", []).append(f.code)
    return {name: sorted({c for cite in lines for c in at.get(cite, [])}) for name, lines in cites.items()}


def evaluate(work: Path, cfg: LlmConfig, ledger: Ledger, mode: Mode = "live", model: object | None = None,
             max_units: int | None = None) -> dict[str, object]:
    cites = plant(work / "data")
    run = stage(build_context(work / "data", CONFIG_DIR))
    assert run.blocked is None, f"the seeded copy no longer runs: {run.blocked}"
    report = run_reasoning(run, cfg, ledger, mode, model, max_units)
    assert report.available
    result = score(report, build_evidence(run), cites)
    return result | {"rules": rules_caught(run, cites)}


def summary(result: dict[str, object]) -> list[str]:
    faults = result["faults"]
    assert isinstance(faults, dict)
    lines = [f"{name}: {f['result']}" + (f" (via {f['via']})" if f["via"] else "") for name, f in faults.items()]
    rules = result["rules"]
    assert isinstance(rules, dict)
    lines = [f"{line}; rules: {', '.join(rules[name]) or 'none'}" for line, name in zip(lines, faults, strict=True)]
    return lines + [f"{result['hits']} of {len(faults)} hit, {len(faults) - int(str(result['hits']))} missed, "
                    f"{result['false_alarms']} false alarms"]


def main() -> int:
    if "--live" not in sys.argv:
        print("this calls the configured model; pass --live to run it")
        return 2
    cfg = load_llm_config()
    out = RUNTIME_DIR / "seeded_faults"
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        result = evaluate(Path(tmp), cfg, Ledger(out / "ledger.jsonl"), "live", None, 120)
    (out / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print("\n".join(summary(result)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
