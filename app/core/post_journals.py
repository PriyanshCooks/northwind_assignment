"""Import lines and journals as postings. Journals post through the entity map; dispositions are set by rule."""
from app.domain.entries import Posting
from app.domain.findings import Finding
from app.domain.journals import Disposition, Journal
from app.domain.ledger import MappedLine
from app.domain.runs import Inputs
from app.parsers.mappings import resolve_account

SUSPENSE = "UNMAPPED"
REJECT_CODES = {"D03": "unbalanced", "D04": "outside the period", "D05": "duplicate"}
HOLD_CODES = {"D06": "account not in the entity chart", "D07": "reversal larger than the balance"}


def import_postings(mapped: list[MappedLine]) -> list[Posting]:
    """One IMPORT posting per trial-balance line. Unmapped lines go to a suspense account so totals are kept."""
    postings = []
    for item in mapped:
        line = item.line
        sources = (line.ref,) if item.map_ref is None else (line.ref, item.map_ref)
        note = f"{line.local_code} {line.local_name.text}"
        if item.verdict == "REMAPPED":
            note += f" (remapped from {line.entity} map to {item.group_code}, assumed)"
        postings.append(Posting(
            entity=line.entity, account=item.group_code or SUSPENSE, amount=line.amount, ccy=line.currency,
            origin="IMPORT", sources=sources, note=note,
        ))
    return postings


def _reasons(journal: Journal, findings: list[Finding], table: dict[str, str]) -> list[str]:
    return [f"{f.code} {table[f.code]}: {f.claim}" for f in findings if f.subject == journal.id and f.code in table]


def decide(journals: list[Journal], findings: list[Finding], assumptions: dict[str, bool | str]) -> list[Disposition]:
    """REJECT when invalid for FY2024 (policy 6), HOLD when a human must look, otherwise POST. Never set by a model."""
    out = []
    in_tb = assumptions.get("journals_in_tb") is True  # assumption A1
    post_held = assumptions.get("held_journals_posted") is True  # assumption A9
    for j in journals:
        reject = _reasons(j, findings, REJECT_CODES)
        hold = _reasons(j, findings, HOLD_CODES)
        if assumptions.get(j.id.lower().replace("-", "")) == "post":  # for example je017 = post (assumption A5)
            reject = [r for r in reject if not r.startswith("D04")]
        if in_tb:
            out.append(Disposition(journal_id=j.id, status="REJECT", reasons=("already in the trial balance (A1)",)))
        elif reject:
            out.append(Disposition(journal_id=j.id, status="REJECT", reasons=tuple(reject)))
        elif hold and not post_held:
            out.append(Disposition(journal_id=j.id, status="HOLD", reasons=tuple(hold)))
        else:
            out.append(Disposition(journal_id=j.id, status="POST", reasons=()))
    return out


def journal_postings(inputs: Inputs, journals: list[Journal], dispositions: list[Disposition]) -> list[Posting]:
    """Postings for the journals that are to be posted, in the entity's own currency, through its map."""
    status = {d.journal_id: d.status for d in dispositions}
    postings = []
    for j in journals:
        if status[j.id] != "POST":
            continue
        for line in j.lines:
            group = resolve_account(inputs.maps, inputs.coa, j.entity, line.account)
            if group is None:
                raise ValueError(f"{j.id} line {line.ref} has no group account but was not held")
            postings.append(Posting(
                entity=j.entity, account=group, amount=line.debit - line.credit, ccy=inputs.entities[j.entity].currency,
                origin="JOURNAL", sources=(line.ref,), note=f"{j.id} {line.account}",
            ))
    return postings
