"""D04 period, D05 duplicate, D06 account exists, D07 reversal larger than the balance."""
from decimal import Decimal

from app.domain.findings import Finding, new_finding
from app.domain.journals import Journal
from app.domain.runs import Context
from app.parsers.mappings import resolve_account


def group_account(ctx: Context, entity: str, account: str) -> str | None:
    return resolve_account(ctx.inputs.maps, ctx.inputs.coa, entity, account)


def d04_period(ctx: Context) -> list[Finding]:
    start, end = ctx.policy.period.start, ctx.policy.period.end
    found = []
    for j in ctx.inputs.journals:
        if not start <= j.date <= end:
            claim = f"{j.id} is dated {j.date}, outside {start} to {end}; policy 6 says it is not posted"
            found.append(new_finding("D04", "BLOCK", claim, j.ref.file, j.ref.line, "blocked", j.total_debit(),
                                     "date", (j.ref,), subject=j.id))
    return found


def _signature(j: Journal) -> tuple[object, ...]:
    return j.entity, j.date, tuple(sorted((line.account, line.debit, line.credit) for line in j.lines))


def d05_duplicate(ctx: Context) -> list[Finding]:
    """The earliest id survives (assumption A6); later journals with identical postings are flagged."""
    seen: dict[tuple[object, ...], Journal] = {}
    found = []
    for j in ctx.inputs.journals:
        first = seen.setdefault(_signature(j), j)
        if first is not j:
            claim = f"{j.id} repeats the postings of {first.id} (same entity, date, accounts and amounts)"
            found.append(new_finding("D05", "BLOCK", claim, j.ref.file, j.ref.line, "blocked", j.total_debit(),
                                     "duplicate", (j.ref, first.ref), subject=j.id))
    return found


def d06_account_exists(ctx: Context) -> list[Finding]:
    found = []
    for j in ctx.inputs.journals:
        for line in j.lines:
            if group_account(ctx, j.entity, line.account) is None:
                claim = (f"{j.id} posts to {line.account}, which is not in the {j.entity} chart or its map; "
                         "it cannot be posted and is held")
                found.append(new_finding("D06", "BLOCK", claim, line.ref.file, line.ref.line, "blocked",
                                         line.debit + line.credit, "account", (line.ref,), subject=j.id))
    return found


def _opening_balances(ctx: Context) -> dict[tuple[str, str], Decimal]:
    balances: dict[tuple[str, str], Decimal] = {}
    for entity, lines in ctx.inputs.trial_balances.items():
        for line in lines:
            key = (entity, line.local_code)
            balances[key] = balances.get(key, Decimal(0)) + line.amount
    return balances


def d07_reversal_exceeds_balance(ctx: Context) -> list[Finding]:
    """A journal line that takes a balance-sheet account past zero to the wrong side, in file order."""
    balances = _opening_balances(ctx)
    found = []
    for j in ctx.inputs.journals:
        if any(group_account(ctx, j.entity, line.account) is None for line in j.lines):
            continue
        for line in j.lines:
            group = ctx.inputs.coa[group_account(ctx, j.entity, line.account) or ""]
            key = (j.entity, line.account)
            before = balances.get(key, Decimal(0))
            after = before + line.debit - line.credit
            balances[key] = after
            flips = (after > 0 >= before) if group.normal_balance == "Credit" else (after < 0 <= before)
            if group.statement == "BS" and flips:
                claim = (f"{j.id} moves {line.account} from {before} to {after}, past zero against its normal "
                         f"{group.normal_balance.lower()} side")
                found.append(new_finding("D07", "BLOCK", claim, line.ref.file, line.ref.line, "blocked",
                                         line.debit + line.credit, "reversal", (line.ref,), subject=j.id))
    return found
