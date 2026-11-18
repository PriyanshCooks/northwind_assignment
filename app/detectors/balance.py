"""D01 trial balance and D03 journal balance."""
from decimal import Decimal

from app.domain.findings import Finding, new_finding
from app.domain.ledger import LedgerLine
from app.domain.runs import Context


def _likely_cause(lines: list[LedgerLine], total: Decimal) -> tuple[str, LedgerLine | None]:
    """A one-line slip explains the gap in three ways: a sign turned over (that line is half the gap), a line added
    twice (it equals the gap) or a line gone (a line of the opposite amount is missing). Said as a hint, never a fix."""
    flipped = [line for line in lines if line.amount * 2 == total]
    repeated = [line for line in lines if line.amount == total]
    if flipped:
        where = ", ".join(f"line {line.ref.line} ({line.local_code})" for line in flipped)
        return f"; turning over the sign of {where} would balance it", flipped[0] if len(flipped) == 1 else None
    if repeated:
        where = ", ".join(f"line {line.ref.line} ({line.local_code})" for line in repeated)
        return f"; {where} equals the gap on its own", repeated[0] if len(repeated) == 1 else None
    return f"; a line of {-total} may be missing", None


def d01_trial_balance(ctx: Context) -> list[Finding]:
    found = []
    for entity, lines in ctx.inputs.trial_balances.items():
        total = sum((line.amount for line in lines), Decimal(0))
        if total != 0:
            hint, line = _likely_cause(lines, total)
            claim = f"{entity} trial balance does not balance: debits less credits is {total}{hint}"
            found.append(new_finding("D01", "BLOCK", claim, ctx.inputs.entities[entity].tb_file,
                                     line.ref.line if line else None, "blocked", abs(total), "tb_sum",
                                     (line.ref,) if line else ()))
    return found


def d03_journal_balance(ctx: Context) -> list[Finding]:
    found = []
    for journal in ctx.inputs.journals:
        debit, credit = journal.total_debit(), journal.total_credit()
        if debit != credit:
            claim = f"{journal.id} is unbalanced: debits {debit}, credits {credit}"
            found.append(new_finding("D03", "BLOCK", claim, journal.ref.file, journal.ref.line, "blocked",
                                     abs(debit - credit), "balance", evidence=(journal.ref,), subject=journal.id))
    return found
