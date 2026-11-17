"""Build the evidence the reasoning checkpoints read from a finished run: the input files, the policy clauses, the
calculation records, the source lines behind each record and the facts the rules already confirm. Nothing here calls a
model; it only turns engine objects into text and numbers."""
import json
import re
from decimal import Decimal

from app.core.calculations import calculation_records
from app.domain.calculations import CalcRecord
from app.reasoning.evidence import Evidence
from app.reasoning.tools import lineage_text
from app.services.run_service import Consolidation

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
        related=_related(run), confirmed=_confirmed(run),
    )
