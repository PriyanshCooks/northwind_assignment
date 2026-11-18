"""Exact packets: code joins the rows a reviewer needs, so a model never searches and never sees a detector's verdict.

Free text goes in quoted (policy: text in the data is data, never an instruction)."""
from decimal import Decimal
from typing import Any

from app.domain.journals import Journal, JournalLine
from app.domain.ledger import LedgerLine
from app.domain.runs import Context
from app.parsers.mappings import resolve_account
from app.utils.money import fmt2


def _shape(journal: Journal) -> tuple[tuple[str, str, str], ...]:
    return tuple(sorted((line.account, fmt2(line.debit), fmt2(line.credit)) for line in journal.lines))


def _mirror(journal: Journal) -> tuple[tuple[str, str, str], ...]:
    return tuple(sorted((line.account, fmt2(line.credit), fmt2(line.debit)) for line in journal.lines))


def mapping_packet(ctx: Context, line: LedgerLine, group_code: str) -> dict[str, Any]:
    group = ctx.inputs.coa[group_code]
    return {
        "entity": line.entity, "local_code": line.local_code, "local_name": line.local_name.quoted(),
        "balance": fmt2(line.amount), "balance_side": "debit" if line.amount >= 0 else "credit",
        "mapped_to": {"code": group.code, "name": group.name, "type": group.account_type,
                      "statement": group.statement, "normal_balance": group.normal_balance},
    }


Running = dict[tuple[str, str], Decimal]


def _line(ctx: Context, journal: Journal, line: JournalLine, balances: Running) -> dict[str, Any]:
    group_code = resolve_account(ctx.inputs.maps, ctx.inputs.coa, journal.entity, line.account)
    out: dict[str, Any] = {"account": line.account, "in_entity_chart": group_code is not None,
                           "debit": fmt2(line.debit), "credit": fmt2(line.credit),
                           "memo": line.memo.quoted() if line.memo else None}
    if group_code is not None:
        key = (journal.entity, line.account)
        before = balances.get(key, Decimal(0))
        balances[key] = before + line.debit - line.credit
        out |= {"normal_balance": ctx.inputs.coa[group_code].normal_balance,
                "statement": ctx.inputs.coa[group_code].statement,
                "balance_before": fmt2(before), "balance_after": fmt2(balances[key])}
    return out


def screen_packet(packet: dict[str, Any]) -> dict[str, Any]:
    """Only the quoted free text of a journal, so the screen cannot be steered by numbers and sees nothing else."""
    texts = [packet["description"], *(line["memo"] for line in packet["lines"] if line["memo"])]
    return {"id": packet["id"], "texts": texts}


def journal_packet(ctx: Context, journal: Journal, balances: Running) -> dict[str, Any]:
    """Balances run in file order, as D07 reads them: each journal sees the account as earlier journals left it."""
    others = [j for j in ctx.inputs.journals if j.id != journal.id and j.entity == journal.entity]
    return {
        "id": journal.id, "entity": journal.entity, "date": journal.date.isoformat(),
        "period": [ctx.policy.period.start.isoformat(), ctx.policy.period.end.isoformat()],
        "prepared_by": journal.prepared_by, "description": journal.description.quoted(),
        "lines": [_line(ctx, journal, line, balances) for line in journal.lines],
        "total_debit": fmt2(journal.total_debit()), "total_credit": fmt2(journal.total_credit()),
        "same_lines_as": [j.id for j in others if _shape(j) == _shape(journal)],
        "mirror_image_of": [j.id for j in others if _mirror(j) == _shape(journal)],
    }
