"""Build the evidence the reasoning checkpoints read from a finished run: the input files, the policy clauses, the
calculation records, the source lines behind each record and the facts the rules already confirm. Nothing here calls a
model; it only turns engine objects into text and numbers."""
import json
import re
from dataclasses import dataclass
from decimal import Decimal
from statistics import median

from app.core.calculations import calculation_records
from app.detectors.mapping import classified, name_nature
from app.detectors.rates import CHECKED_TYPES, percent_apart
from app.domain.calculations import CalcRecord
from app.llm.client import Mode
from app.llm.factory import LlmConfig
from app.llm.ledger import Ledger
from app.reasoning.budget import UnitBudget
from app.reasoning.calc_review import CalcReport, review_calculations
from app.reasoning.evidence import Evidence
from app.reasoning.grounding import Grounded
from app.reasoning.investigator import TraceReport, investigate
from app.reasoning.reader import InputReport, read_inputs
from app.reasoning.tools import lineage_text
from app.services.run_service import Consolidation
from app.utils.money import to_decimal

CLAUSE = re.compile(r"^(\d+)\. ", re.MULTILINE)


def policy_rules(text: str) -> dict[str, str]:
    """`policy N` -> the clause as written, including its indented sub-points."""
    marks = list(CLAUSE.finditer(text))
    ends = [m.start() for m in marks[1:]] + [len(text)]
    return {f"policy {m.group(1)}": text[m.end():end].strip() for m, end in zip(marks, ends, strict=True)}


def _related(run: Consolidation) -> dict[str, str]:
    out: dict[str, list[str]] = {}
    for m in run.mapped:
        if m.group_code is not None:
            line = m.line
            out.setdefault(m.group_code, []).append(
                f"{line.entity} {line.local_code} {line.local_name.quoted()} balance {line.amount} ({line.ref})")
    coa = run.ctx.inputs.coa
    return {code: f"{coa[code].name if code in coa else code}\n" + "\n".join(lines) for code, lines in out.items()}


def _shown(value: Decimal) -> str:
    """Four decimals at most, so a model can quote a number exactly as it is written in the record."""
    return format(value.quantize(Decimal("0.0001")).normalize(), "f")


def record_text(record: CalcRecord) -> str:
    """The record as the model sees it. The full-precision result stays in `Evidence.results` for code."""
    data = record.model_dump(mode="json")
    data["result"] = _shown(record.result)
    for item, original in zip(data["inputs"], record.inputs, strict=True):
        item["value"] = _shown(original.value)
    return json.dumps(data)


def _confirmed(run: Consolidation) -> dict[str, frozenset[str]]:
    """Facts the detectors already proved, by file:line, so a model claim that matches one is verified."""
    nature = {f"{f.file}:{f.line}" for f in run.findings if f.code == "D02" and "nature" in f.key and f.line}
    rates = {f"{f.file}:{f.line}" for f in run.findings if f.code in {"D08", "D15"} and f.file == "fx_rates.csv"
             and f.line}
    return {"nature_mismatch": frozenset(nature), "unit_or_direction_suspect": frozenset(rates)}


def _rate_gaps(run: Consolidation) -> dict[str, Decimal]:
    """The D15 measure for every checked rate row, so a claim about a rate can be tested against it."""
    rows, out = run.ctx.inputs.rates, {}
    for row in rows:
        others = [r.value for r in rows if (r.base, r.quote) == (row.base, row.quote) and r is not row]
        if row.rate_type in CHECKED_TYPES and others:
            out[str(row.ref)] = percent_apart(row.value, median(others))
    return out


def _nature_agrees(run: Consolidation) -> frozenset[str]:
    """Map rows whose name reads as a nature and whose group account has it (the opposite of D02's nature finding)."""
    coa, agree = run.ctx.inputs.coa, set()
    for m in classified(run.ctx):
        nature = name_nature(m.line.local_name.text)
        if m.verdict == "OK" and m.group_code in coa and m.map_ref and nature:
            if coa[m.group_code].account_type == nature[1]:
                agree.add(str(m.map_ref))
    return frozenset(agree)


def build_evidence(run: Consolidation) -> Evidence:
    data_dir = run.ctx.inputs.data_dir
    files = frozenset(p.name for p in data_dir.iterdir() if p.is_file())
    records = calculation_records(run)
    sources = {r.id: "; ".join(i.source for i in r.inputs if not i.source.startswith("calc:")) for r in records}
    return Evidence(
        data_dir=data_dir, files=files, last_year=run.ctx.policy.period.end.year,
        rules=policy_rules((data_dir / "group_policies.md").read_text(encoding="utf-8")),
        calculations={r.id: record_text(r) for r in records},
        results={r.id: r.result if isinstance(r.result, Decimal) else Decimal(str(r.result)) for r in records},
        lineage={rid: lineage_text(data_dir, src, files) for rid, src in sources.items()},
        related=_related(run), confirmed=_confirmed(run), rate_gaps=_rate_gaps(run),
        rate_tolerance=to_decimal(run.ctx.assumptions["rate_neighbour_tolerance_pct"]),
        nature_agrees=_nature_agrees(run),
        normal_sides={r.id: r.normal_side for r in records if r.normal_side},
    )


NOT_AVAILABLE = ("AI review not available: the local model cannot do reliable tool use, so the reasoning layer runs "
                 "on a cloud model only. The rules and every figure are unchanged.")


@dataclass
class ReasoningReport:
    """Advice only. Nothing here is read by the engine, a gate or a writer."""

    available: bool
    note: str = ""
    inputs: InputReport | None = None
    calcs: CalcReport | None = None
    traces: TraceReport | None = None


def run_reasoning(
    run: Consolidation, cfg: LlmConfig, ledger: Ledger, mode: Mode = "replay", model: object | None = None,
    max_units: int | None = None, smoke: bool = False,
) -> ReasoningReport:
    """The three checkpoints in order. `max_units` limits live units for the whole run; `smoke` sends one unit to
    each checkpoint, which is enough to see a provider accept the schema and the tools."""
    if cfg.model.startswith("ollama:") and model is None:
        return ReasoningReport(False, NOT_AVAILABLE)
    evidence = build_evidence(run)
    shared = UnitBudget(max_units)

    def budget() -> UnitBudget:
        return UnitBudget(1) if smoke else shared

    inputs = read_inputs(cfg, ledger, evidence, mode, model, budget())
    calcs = review_calculations(cfg, ledger, evidence, mode, model, budget())
    if smoke and not calcs.concerns() and evidence.calculations:
        first = next(iter(evidence.calculations))
        calcs.findings.append(Grounded(first, "magnitude_implausible", "smoke test of the investigator", "suspicion"))
    traces = investigate(cfg, ledger, evidence, calcs, mode, model, budget())
    return ReasoningReport(True, "", inputs, calcs, traces)
