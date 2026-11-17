"""Human decisions on findings: which overrides apply, which are stale, and the review queue."""
import re
from dataclasses import dataclass
from pathlib import Path

from app.domain.findings import Finding
from app.domain.policy import Override
from app.domain.runs import Inputs
from app.parsers.mappings import classify_all
from app.utils.hashing import json_hash


@dataclass(frozen=True)
class OverrideState:
    """`applied` and `open` change the run; `stale` and `rejected` do not."""

    override: Override
    state: str


def evidence_hash(inputs: Inputs, target: str) -> str | None:
    """What the reviewer looked at: the mapping row and the trial balance row of 'mapping:UK:2310'."""
    kind, entity, code = target.split(":")
    if kind != "mapping":
        return None
    for line in classify_all(inputs.trial_balances, inputs.maps, inputs.coa):
        if (line.line.entity, line.line.local_code) == (entity, code) and line.map_ref is not None:
            return json_hash([line.map_ref.row_hash, line.line.ref.row_hash])
    return None


def override_states(rows: list[Override], inputs: Inputs) -> list[OverrideState]:
    """A decision made on evidence that has since changed is stale: it stops applying and returns to the queue."""
    states = []
    for row in rows:
        if row.status == "rejected":
            states.append(OverrideState(row, "rejected"))
        elif row.evidence_hash != evidence_hash(inputs, row.target):
            states.append(OverrideState(row, "stale"))
        else:
            states.append(OverrideState(row, "applied" if row.status == "approved" else "open"))
    return states


def active_overrides(rows: list[Override], inputs: Inputs) -> list[Override]:
    return [s.override for s in override_states(rows, inputs) if s.state in {"applied", "open"}]


def review_queue(findings: list[Finding], states: list[OverrideState]) -> list[dict[str, str]]:
    """Open and stale overrides first, then every finding a person still has to look at. Notes are not queued."""
    queue = [{"kind": "override", "key": s.override.target, "state": s.state, "reason": s.override.reason}
             for s in states if s.state in {"open", "stale"}]
    for f in findings:
        mapping_decided = f.code == "D02" and f.action == "assumed" and bool(states)
        if f.severity != "NOTE" and not mapping_decided:
            queue.append({"kind": "finding", "key": f.key, "state": f.action, "reason": f.claim})
    return queue


def approve(path: Path, inputs: Inputs, target: str, approver: str) -> None:
    """Sign a decision off on the evidence as it stands now: sets approver, status and evidence_hash in the file."""
    _rewrite(path, target, {"approver": approver, "status": "approved", "evidence_hash": evidence_hash(inputs, target)})


def reject(path: Path, target: str, approver: str) -> None:
    _rewrite(path, target, {"approver": approver, "status": "rejected"})


def _rewrite(path: Path, target: str, fields: dict[str, str | None]) -> None:
    text = path.read_text(encoding="utf-8")
    blocks = re.split(r"(?m)^(?=\[\[override\]\])", text)
    for i, block in enumerate(blocks):
        if f'target = "{target}"' not in block:
            continue
        for name, value in fields.items():
            line = f'{name} = "{value}"'
            pattern = rf'(?m)^{name} = ".*"$'
            block = re.sub(pattern, line, block) if re.search(pattern, block) else block.rstrip("\n") + f"\n{line}\n"
        blocks[i] = block
        path.write_text("".join(blocks), encoding="utf-8", newline="")
        return
    raise KeyError(f"no override for {target}")
