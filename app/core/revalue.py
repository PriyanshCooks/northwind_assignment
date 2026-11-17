"""Foreign-currency items inside an entity's own books at the closing rate (policy 3)."""
from dataclasses import dataclass
from decimal import Decimal

from app.domain.entries import Entry, Posting
from app.domain.ledger import LedgerLine, MappedLine
from app.parsers.fx_rates import FxTable

# policy 3 restates monetary items only: cash, receivables, payables, accruals, tax and borrowings
MONETARY = {"1100", "1200", "1250", "2100", "2150", "2200", "2400", "2500"}


@dataclass
class RevalueResult:
    entries: list[Entry]
    unresolved: list[LedgerLine]


def restated_amount(line: LedgerLine, fx: FxTable) -> Decimal | None:
    """The line's foreign amount in the entity's functional currency at closing; None without a closing rate."""
    if line.txn_ccy is None or line.txn_amount is None:
        return None
    foreign, home = fx.units_per_gbp(line.txn_ccy, "closing"), fx.units_per_gbp(line.currency, "closing")
    if foreign is None or home is None:
        return None
    return line.txn_amount / foreign * home


def revalue(mapped: list[MappedLine], fx: FxTable, difference_account: str) -> RevalueResult:
    """Dr or Cr the item and the opposite to the policy difference account (7300). A line with no closing rate
    is left alone and reported."""
    entries: list[Entry] = []
    unresolved: list[LedgerLine] = []
    for item in mapped:
        line = item.line
        if item.group_code not in MONETARY or line.txn_ccy is None:
            continue
        restated = restated_amount(line, fx)
        if restated is None:
            unresolved.append(line)
            continue
        difference = restated - line.amount
        if difference == 0:
            continue
        rate = fx.ref(line.txn_ccy, "closing")
        note = f"{line.local_code} {line.txn_ccy} {line.txn_amount} at closing"
        sources = (line.ref,)
        entries.append(Entry(
            id=f"REV-{line.entity}-{line.local_code}", origin="REVALUE", description=f"Revalue {note}",
            lines=(
                Posting(entity=line.entity, account=item.group_code or "", amount=difference, ccy=line.currency,
                        origin="REVALUE", sources=sources, rate_ref=rate, note=note),
                Posting(entity=line.entity, account=difference_account, amount=-difference, ccy=line.currency,
                        origin="REVALUE", sources=sources, rate_ref=rate, note=note),
            ),
        ))
    return RevalueResult(entries, unresolved)
