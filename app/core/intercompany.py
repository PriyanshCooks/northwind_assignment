"""Pair intercompany invoices, record the one in transit, and split the difference into its causes (policy 5)."""
from dataclasses import dataclass
from decimal import Decimal

from app.domain.entries import Entry, Posting
from app.domain.runs import IcInvoice, Inputs
from app.parsers.fx_rates import FxTable

# group chart: a management fee is income 4200 for the charging entity and expense 6300 for the charged one
IC_PAYABLE, IC_EXPENSE = "2150", "6300"


@dataclass
class IcResult:
    entries: list[Entry]
    in_transit: list[IcInvoice]
    difference: Decimal | None
    causes: dict[str, Decimal]


def _pairs(invoices: list[IcInvoice]) -> tuple[list[IcInvoice], list[IcInvoice]]:
    """(charged by one entity and booked by the other, charged but not booked by the counterparty)."""
    booked = {(i.reporting_entity, i.doc_ref) for i in invoices}
    matched = [i for i in invoices if (i.counterparty, i.doc_ref) in booked]
    return matched, [i for i in invoices if (i.counterparty, i.doc_ref) not in booked and i.reporting_entity == "US"]


def reconcile(inputs: Inputs, fx: FxTable) -> IcResult:
    """The charging side is the entity that reports the invoice first (the US); the receiving side books it.
    An invoice the receiver has not booked is recorded by the receiver at the closing rate (policy 5)."""
    charged = [i for i in inputs.intercompany if i.reporting_entity == "US"]
    booked = [i for i in inputs.intercompany if i.reporting_entity != "US"]
    matched, transit = _pairs(inputs.intercompany)
    closing = {i.doc_ref: fx.to_gbp(i.doc_amount, i.doc_currency, "closing") for i in charged}
    if any(v is None for v in closing.values()):
        return IcResult([], transit, None, {})
    known = {k: v for k, v in closing.items() if v is not None}
    receivable = sum(known.values(), Decimal(0))
    payable_booked = sum((i.booked_amount for i in booked), Decimal(0))
    in_transit = sum((known[i.doc_ref] for i in transit), Decimal(0))
    matched_charged = sum((known[i.doc_ref] for i in matched if i.reporting_entity == "US"), Decimal(0))
    causes = {"in_transit": in_transit, "revaluation": matched_charged - payable_booked}
    entries = [_transit_entry(i, known[i.doc_ref], inputs, fx) for i in transit]
    return IcResult(entries, transit, receivable - payable_booked, causes)


def _transit_entry(inv: IcInvoice, gbp: Decimal, inputs: Inputs, fx: FxTable) -> Entry:
    receiver = inputs.entities[inv.counterparty]
    home = fx.units_per_gbp(receiver.currency, "closing") or Decimal(1)
    amount = gbp * home
    rate = fx.ref(inv.doc_currency, "closing")
    note = f"{inv.doc_ref} {inv.doc_currency} {inv.doc_amount} in transit, recorded by {receiver.id} at closing"

    def leg(account: str, signed: Decimal) -> Posting:
        return Posting(entity=receiver.id, account=account, amount=signed, ccy=receiver.currency,
                       origin="ELIMINATION", sources=(inv.ref,), rate_ref=rate, note=note)

    return Entry(id=f"IC-TRANSIT-{inv.doc_ref}", origin="ELIMINATION", description=note,
                 lines=(leg(IC_EXPENSE, amount), leg(IC_PAYABLE, -amount)))
