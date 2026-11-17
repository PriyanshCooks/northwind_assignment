"""The units a reviewer is asked about: one per trial-balance line and one per journal."""
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.detectors.mapping import classified
from app.domain.runs import Context
from app.review.packets import journal_packet, mapping_packet


@dataclass(frozen=True)
class Unit:
    kind: str  # "mapping" or "journal"
    unit_id: str
    packet: dict[str, Any]


def mapping_units(ctx: Context) -> list[Unit]:
    """Lines that have a group account. The group code is as supplied in the map file, not what a detector decided."""
    return [Unit("mapping", f"{m.line.entity}:{m.line.local_code}:{m.line.ref.line}",
                 mapping_packet(ctx, m.line, m.group_code or m.proposed_group_code or ""))
            for m in classified(ctx) if m.map_ref is not None and (m.group_code or m.proposed_group_code)]


def journal_units(ctx: Context) -> list[Unit]:
    balances: dict[tuple[str, str], Decimal] = {}
    for entity, lines in ctx.inputs.trial_balances.items():
        for line in lines:
            balances[(entity, line.local_code)] = balances.get((entity, line.local_code), Decimal(0)) + line.amount
    return [Unit("journal", j.id, journal_packet(ctx, j, balances)) for j in ctx.inputs.journals]
