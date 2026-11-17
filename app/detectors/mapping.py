"""D02 mapping: completeness, ambiguity, target exists, nature against type, sign against normal balance."""
import re

from app.domain.findings import Finding, new_finding
from app.domain.ledger import MappedLine
from app.domain.runs import Context
from app.parsers.mappings import classify_all, remap_switch

LIABILITY_NAME = re.compile(
    r"\b(deferred|unearned|accruals?|accrued|payables?|creditors?|due to|loans?|borrowings?|provisions?)\b",
    re.IGNORECASE)
INCOME_NAME = re.compile(r"\b(revenue|turnover|sales|income)\b", re.IGNORECASE)
NOT_INCOME = re.compile(r"\b(cost|costs|expenses?|tax|deferred|unearned|payables?|due to)\b", re.IGNORECASE)


def classified(ctx: Context) -> list[MappedLine]:
    return classify_all(ctx.inputs.trial_balances, ctx.inputs.maps, ctx.inputs.coa)


def _problem(ctx: Context, mapped: MappedLine) -> Finding | None:
    line, tb_file = mapped.line, mapped.line.ref.file
    amount = abs(line.amount)
    if mapped.verdict == "UNMAPPED":
        claim = f"{line.entity} account {line.local_code} has no usable group mapping; carried as UNMAPPED"
        return new_finding("D02", "FLAG", claim, tb_file, line.ref.line, "flagged", amount, "unmapped", (line.ref,))
    if mapped.verdict == "AMBIGUOUS":
        claim = f"{line.entity} account {line.local_code} maps to more than one group account"
        return new_finding("D02", "BLOCK", claim, tb_file, line.ref.line, "blocked", amount, "ambiguous", (line.ref,))
    if mapped.verdict == "SUSPECT" and mapped.map_ref is not None:
        switch = ctx.assumptions.get(remap_switch(line.entity, line.local_code))
        approved = switch == f"remap_{mapped.proposed_group_code}"
        claim = (f"{line.entity} {line.local_code} is mapped to {mapped.group_code} but its name equals group account "
                 f"{mapped.proposed_group_code}; " + ("remapped as assumed" if approved else "applied as supplied"))
        return new_finding("D02", "FLAG", claim, mapped.map_ref.file, mapped.map_ref.line,
                           "assumed" if approved else "flagged", amount, "nature", (mapped.map_ref, line.ref))
    return None


def _nature_problem(mapped: MappedLine, ctx: Context) -> Finding | None:
    """Policy 4: the account nature decides, not an exact name. A liability-like name mapped to a group account that is
    not a liability, or an income-like name mapped to one that is not revenue, is flagged and left as supplied."""
    if mapped.verdict != "OK" or mapped.group_code is None:
        return None  # a suspect or unmapped line already has its own finding
    line, account = mapped.line, ctx.inputs.coa[mapped.group_code]
    name = line.local_name.text
    if LIABILITY_NAME.search(name):
        reads_as, expected = "a liability", "Liability"
    elif INCOME_NAME.search(name) and not NOT_INCOME.search(name):
        reads_as, expected = "income", "Revenue"
    else:
        return None
    if account.account_type == expected:
        return None
    place = mapped.map_ref or line.ref
    claim = (f"{line.entity} {line.local_code} is named '{name}', which reads as {reads_as}, but it is mapped to group "
             f"account {account.code} ({account.account_type}); applied as supplied")
    return new_finding("D02", "FLAG", claim, place.file, place.line, "flagged", abs(line.amount), "nature_name",
                       tuple(r for r in (mapped.map_ref, line.ref) if r is not None))


def _sign_problem(ctx: Context, mapped: MappedLine) -> Finding | None:
    if mapped.group_code is None or mapped.line.amount == 0:
        return None
    account = ctx.inputs.coa[mapped.group_code]
    wrong_side = (account.normal_balance == "Debit") == (mapped.line.amount < 0)
    if not wrong_side:
        return None
    line = mapped.line
    claim = f"{line.entity} {line.local_code} has a balance against the normal side of group account {account.code}"
    return new_finding("D02", "NOTE", claim, line.ref.file, line.ref.line, "noted", abs(line.amount), "sign",
                       (line.ref,))


def d02_mapping(ctx: Context) -> list[Finding]:
    found = []
    for mapped in classified(ctx):
        checks = (_problem(ctx, mapped), _nature_problem(mapped, ctx), _sign_problem(ctx, mapped))
        found += [f for f in checks if f is not None]
    return found
