"""D01 trial balance and D03 journal balance."""
from decimal import Decimal

from app.domain.findings import Finding, new_finding
from app.domain.runs import Context


def d01_trial_balance(ctx: Context) -> list[Finding]:
    found = []
    for entity, lines in ctx.inputs.trial_balances.items():
        total = sum((line.amount for line in lines), Decimal(0))
        if total != 0:
            claim = f"{entity} trial balance does not balance: debits less credits is {total}"
            found.append(new_finding("D01", "BLOCK", claim, ctx.inputs.entities[entity].tb_file, None, "blocked",
                                     abs(total), "tb_sum"))
    return found


def d03_journal_balance(ctx: Context) -> list[Finding]:
    found = []
    for journal in ctx.inputs.journals:
        debit, credit = journal.total_debit(), journal.total_credit()
        if debit != credit:
            claim = f"{journal.id} is unbalanced: debits {debit}, credits {credit}"
            found.append(new_finding("D03", "BLOCK", claim, journal.ref.file, journal.ref.line, "blocked",
                                     abs(debit - credit), "balance", evidence=(journal.ref,)))
    return found
