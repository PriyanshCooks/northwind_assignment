"""D02 mapping: completeness, ambiguity, target exists, nature against type, sign against normal balance."""
from app.domain.findings import Finding, new_finding
from app.domain.ledger import MappedLine
from app.domain.runs import Context
from app.parsers.mappings import classify


def remap_switch(entity: str, local_code: str) -> str:
    """The assumptions key that approves a rule-confirmed remap, for example map_uk_2310 (assumption A7)."""
    return f"map_{entity.lower()}_{local_code}"


def classified(ctx: Context) -> list[MappedLine]:
    out = []
    for entity, lines in ctx.inputs.trial_balances.items():
        index = ctx.inputs.maps.get(entity)
        for line in lines:
            rows = None if index is None else index.get(line.local_code, [])
            out.append(classify(line, rows, ctx.inputs.coa))
    return out


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
        found += [f for f in (_problem(ctx, mapped), _sign_problem(ctx, mapped)) if f is not None]
    return found
