"""D09 sub-ledger, D10 cross-file tie-outs, D11 intercompany pairing."""
from decimal import Decimal

from app.detectors.mapping import classified
from app.domain.findings import Finding, new_finding
from app.domain.runs import Context, IcInvoice
from app.parsers.acquisition_note import table_foots
from app.parsers.fx_rates import FxTable

# control ledger name -> (group account holding it, sign that makes the TB balance positive)
CONTROLS = {"Accounts receivable (trade)": ("1200", 1), "Accounts payable (trade)": ("2100", -1)}
TIE_TOLERANCE = Decimal("0.01")  # assumption A12: the supplied opening equity is rounded to the cent


def _group_total(ctx: Context, entity: str, group: str) -> Decimal:
    mine = (m.line.amount for m in classified(ctx) if m.line.entity == entity and m.group_code == group)
    return sum(mine, Decimal(0))


def d09_subledger(ctx: Context) -> list[Finding]:
    """Checked on the unadjusted trial balance, before any journal."""
    found = []
    for control in ctx.inputs.subledger:
        group, sign = CONTROLS[control.ledger]
        book = sign * _group_total(ctx, control.entity, group)
        if book != control.control_total:
            claim = (f"{control.entity} {control.ledger}: trial balance {book} against sub-ledger "
                     f"{control.control_total} {control.currency}; not adjusted")
            found.append(new_finding("D09", "FLAG", claim, control.ref.file, control.ref.line, "flagged",
                                     abs(book - control.control_total), "control_total", (control.ref,)))
    return found


def _monthly_ties(ctx: Context) -> list[Finding]:
    found = []
    tb = {line.local_code: line for line in ctx.inputs.trial_balances["IN"]}
    for code in sorted({row.ledger_code for row in ctx.inputs.india_monthly}):
        total = sum((r.amount for r in ctx.inputs.india_monthly if r.ledger_code == code), Decimal(0))
        line = tb.get(code)
        if line is None or line.amount != total:
            ref = line.ref if line else ctx.inputs.india_monthly[0].ref
            held = line.amount if line else Decimal(0)
            claim = f"India monthly P&L for {code} sums to {total}, trial balance holds {held}"
            found.append(new_finding("D10", "BLOCK", claim, ref.file, ref.line, "blocked", abs(total - held),
                                     f"monthly_{code}", (ref,)))
    return found


def _opening_equity_tie(ctx: Context, fx: FxTable) -> list[Finding]:
    """Opening group equity should equal the entities' opening net assets at the opening rate, within a cent."""
    opening = fx.units_per_gbp("USD", "opening")
    if opening is None or not ctx.inputs.prior_equity:
        return []
    equity = {"US": -(_group_total(ctx, "US", "3100") + _group_total(ctx, "US", "3200")),
              "UK": -(_group_total(ctx, "UK", "3100") + _group_total(ctx, "UK", "3200"))}
    rebuilt = equity["US"] / opening + equity["UK"] - _group_total(ctx, "US", "1600") / opening
    given = sum((p.amount_gbp for p in ctx.inputs.prior_equity.values()), Decimal(0))
    if abs(rebuilt - given) > TIE_TOLERANCE:
        ref = ctx.inputs.prior_equity["3100"].ref
        claim = f"prior_year_group.csv equity {given} does not tie to opening net assets {rebuilt}"
        gap = abs(rebuilt - given)
        return [new_finding("D10", "FLAG", claim, ref.file, ref.line, "flagged", gap, "opening_equity")]
    return []


def d10_cross_file_ties(ctx: Context) -> list[Finding]:
    found = _monthly_ties(ctx)
    note = ctx.inputs.acquisition
    if not table_foots(note):
        ref = note.refs["net_assets"]
        found.append(new_finding("D10", "BLOCK", "the acquisition note table does not foot", ref.file, ref.line,
                                 "blocked", None, "foot", (ref,)))
    fx = FxTable(ctx.inputs.rates)
    spot_inr, spot_usd = fx.units_per_gbp("INR", "spot"), fx.units_per_gbp("USD", "spot")
    if spot_inr and spot_usd:
        expected = note.consideration_inr / (spot_inr / spot_usd)
        booked = _group_total(ctx, "US", "1610")
        if abs(expected - booked) > TIE_TOLERANCE:
            claim = f"US investment in India is {booked}; consideration at the spot rate is {expected}"
            gap = abs(expected - booked)
            found.append(new_finding("D10", "FLAG", claim, "tb_us.csv", None, "flagged", gap, "invest"))
    return found + _opening_equity_tie(ctx, fx)


def _repeats_and_mismatches(ctx: Context) -> list[Finding]:
    """The same document twice for one entity, or the two entities disagreeing on what the document says."""
    found: list[Finding] = []
    seen: dict[tuple[str, str], IcInvoice] = {}
    for inv in ctx.inputs.intercompany:
        first = seen.setdefault((inv.reporting_entity, inv.doc_ref), inv)
        if first is not inv:
            claim = (f"{inv.doc_ref} is listed twice for {inv.reporting_entity} (lines {first.ref.line} and "
                     f"{inv.ref.line}): the second is counted again")
            found.append(new_finding("D11", "FLAG", claim, inv.ref.file, inv.ref.line, "flagged", abs(inv.doc_amount),
                                     "duplicate", (inv.ref, first.ref)))
    for (entity, doc_ref), inv in seen.items():
        other = seen.get((inv.counterparty, doc_ref))
        if other is None or entity > inv.counterparty:
            continue
        if (inv.doc_amount, inv.doc_currency) != (other.doc_amount, other.doc_currency):
            claim = (f"{doc_ref}: {entity} says {inv.doc_currency} {inv.doc_amount}, {inv.counterparty} says "
                     f"{other.doc_currency} {other.doc_amount}")
            found.append(new_finding("D11", "FLAG", claim, other.ref.file, other.ref.line, "flagged",
                                     abs(inv.doc_amount - other.doc_amount), "mismatch", (inv.ref, other.ref)))
    return found


def d11_intercompany_pairing(ctx: Context) -> list[Finding]:
    fx = FxTable(ctx.inputs.rates)
    by_side: dict[str, dict[str, object]] = {}
    for inv in ctx.inputs.intercompany:
        by_side.setdefault(inv.reporting_entity, {})[inv.doc_ref] = inv
    found = _repeats_and_mismatches(ctx)
    for inv in ctx.inputs.intercompany:
        other = by_side.get(inv.counterparty, {}).get(inv.doc_ref)
        if other is None:
            gbp = fx.to_gbp(inv.doc_amount, inv.doc_currency, "closing")
            claim = (f"{inv.doc_ref} ({inv.doc_currency} {inv.doc_amount}) is booked by {inv.reporting_entity} but "
                     f"not by {inv.counterparty}: in transit at the year end, recorded at the closing rate (policy 5)")
            found.append(new_finding("D11", "FLAG", claim, inv.ref.file, inv.ref.line, "assumed", gbp, "unpaired",
                                     (inv.ref,)))
    return found
