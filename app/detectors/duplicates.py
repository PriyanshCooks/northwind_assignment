"""D14 exact duplicate trial-balance rows. Flagged, never dropped."""
from app.domain.findings import Finding, new_finding
from app.domain.ledger import LedgerLine
from app.domain.runs import Context


def d14_exact_duplicates(ctx: Context) -> list[Finding]:
    """Two UK wage rows with the same amount are legitimate: they differ by cost centre, which is part of the key."""
    found = []
    for entity, lines in ctx.inputs.trial_balances.items():
        seen: dict[tuple[object, ...], LedgerLine] = {}
        for line in lines:
            key = (line.local_code, line.local_name.text, line.cost_centre, line.amount, line.txn_ccy, line.txn_amount)
            first = seen.setdefault(key, line)
            if first is not line:
                claim = f"{entity} row {line.ref.line} repeats row {first.ref.line} exactly (account {line.local_code})"
                found.append(new_finding("D14", "FLAG", claim, line.ref.file, line.ref.line, "flagged",
                                         abs(line.amount), "duplicate", (line.ref, first.ref)))
    return found
