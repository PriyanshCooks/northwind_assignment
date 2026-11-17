"""Origin rows: every consolidated balance as the postings it is made of, and a trace for each control figure."""
from decimal import Decimal
from typing import TYPE_CHECKING

from app.domain.entries import Posting, TraceStep
from app.domain.figures import Determined, Provisional

if TYPE_CHECKING:
    from app.services.run_service import Consolidation


def origin_rows(run: "Consolidation") -> list[Posting]:
    """Translated postings plus the non-equity legs of every elimination, the pieces the balances are summed from."""
    coa = run.ctx.inputs.coa
    legs = [leg for entry in run.eliminations for leg in entry.lines
            if leg.account not in coa or coa[leg.account].account_type != "Equity"]
    return list(run.translated) + legs


def _step(
    figure: str, formula: str, inputs: tuple[str, ...], result: Decimal | None, row: Posting | None = None,
) -> TraceStep:
    return TraceStep(figure=figure, formula=formula, inputs=inputs, result=result, sources=row.sources if row else ())


def _rows_for(figure: str, rows: list[Posting], accounts: set[str], sign: int) -> list[TraceStep]:
    return [_step(figure, f"{r.origin} {r.entity} {r.account}: {r.note}", (r.rate_ref or "",), sign * r.amount, r)
            for r in rows if r.account in accounts]


def build_traces(run: "Consolidation") -> dict[str, list[TraceStep]]:
    """A figure is walked down to the postings it sums, and each posting names its file:line sources."""
    coa, rows = run.ctx.inputs.coa, origin_rows(run)
    kinds = lambda t: {c for c, a in coa.items() if a.account_type == t}  # noqa: E731
    pl = {c for c, a in coa.items() if a.statement == "PL"}
    traces: dict[str, list[TraceStep]] = {
        "group_revenue": _rows_for("group_revenue", rows, kinds("Revenue"), -1),
        "group_profit": _rows_for("group_profit", rows, pl, -1),
        "total_assets": _rows_for("total_assets", rows, kinds("Asset"), 1),
    }
    acq = run.acquisition
    if acq is not None:
        spec = acq.refs
        traces["goodwill_closing"] = [
            TraceStep(figure="goodwill_closing", formula="consideration - interest% x net assets at completion",
                      inputs=("acquisition_note.md",), result=acq.goodwill_inr, sources=spec),
            TraceStep(figure="goodwill_closing", formula="goodwill in INR / GBP-INR closing rate (policy 4)",
                      inputs=(f"{acq.closing_rate}",), result=acq.goodwill_gbp, sources=spec),
        ]
        traces["nci_closing"] = [
            TraceStep(figure="nci_closing", formula="NCI% x India net assets (INR) / closing rate (policy 4)",
                      inputs=(f"net assets INR {acq.india_net_assets_inr}",), result=acq.nci_closing,
                      sources=tuple(s for r in run.local if r.entity == "IN" for s in r.sources[:1])),
        ]
        traces["profit_nci"] = [
            TraceStep(figure="profit_nci", formula="NCI% x India profit for the months owned, at the average rate",
                      inputs=(f"India profit GBP {acq.india_profit_gbp}",), result=acq.nci_profit),
        ]
    if run.ic is not None and run.ic.difference is not None:
        traces["intercompany_difference"] = [
            TraceStep(figure="intercompany_difference", formula=f"cause: {name}", inputs=(), result=value,
                      sources=tuple(i.ref for i in run.ic.in_transit) if name == "in_transit" else ())
            for name, value in run.ic.causes.items()
        ]
    figure = run.figures.get("journals")
    if isinstance(figure, (Determined, Provisional)):
        refs = {j.id: j.ref for j in run.ctx.inputs.journals}
        traces["journals"] = [
            TraceStep(figure="journals", formula=f"{d.journal_id}: {d.status} {'; '.join(d.reasons)}".strip(),
                      inputs=(), result=None, sources=(refs[d.journal_id],))
            for d in run.dispositions
        ]
    return traces
