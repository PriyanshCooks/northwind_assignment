"""Calculation records: for every consolidated row and every control figure, the formula, its inputs with their
file:line and the result. Built after the run from what the engine already computed, so no figure changes."""
from decimal import Decimal
from typing import TYPE_CHECKING, Literal

from app.core.lineage import origin_rows
from app.core.revalue import restated_amount
from app.domain.calculations import CalcInput, CalcRecord
from app.domain.figures import Figure
from app.domain.refs import SourceRef
from app.parsers.fx_rates import FxTable

if TYPE_CHECKING:
    from app.services.run_service import Consolidation

Input = tuple[str, str, Decimal, str]  # name, label, value, source


def _refs(refs: list[SourceRef] | tuple[SourceRef, ...]) -> str:
    return "; ".join(dict.fromkeys(str(r) for r in refs)) or "no source row"


def _record(rid: str, kind: Literal["row", "figure"], label: str, formula: str, inputs: list[Input],
            result: Decimal) -> CalcRecord:
    return CalcRecord(id=rid, kind=kind, label=label, formula=formula, result=result,
                      inputs=tuple(CalcInput(name=n, label=lb, value=v, source=s) for n, lb, v, s in inputs))


def _value(figure: Figure) -> Decimal:
    value = getattr(figure, "value", None)
    if not isinstance(value, Decimal):
        raise ValueError("this figure has no single number")
    return value


def _row_records(run: "Consolidation") -> list[CalcRecord]:
    """One record per non-zero balance: the postings it sums, each with its source rows (policy 2 for the rate)."""
    by_account: dict[str, list[Input]] = {}
    for p in origin_rows(run):
        terms = by_account.setdefault(p.account, [])
        label = f"{p.origin} {p.entity}: {p.note}" + (f" at {p.rate_ref}" if p.rate_ref else "")
        terms.append((f"p{len(terms) + 1}", label, p.amount, _refs(p.sources)))
    return [_record(f"row:{a}", "row", f"balance of {a}", " + ".join(t[0] for t in terms), terms, v)
            for a, terms in sorted(by_account.items()) if (v := run.balances.get(a, Decimal(0))) != 0]


def _equity_rows(run: "Consolidation") -> list[CalcRecord]:
    prior, acq, res = run.ctx.inputs.prior_equity, run.acquisition, run.reserve
    assert acq is not None and res is not None
    pr = {k: (v.amount_gbp, str(v.ref)) for k, v in prior.items()}
    acq_refs = _refs(acq.refs)
    return [
        _record("row:3100", "row", "share capital, opening group equity", "-capital",
                [("capital", "prior-year share capital", *pr["3100"])], -pr["3100"][0]),
        _record("row:3200", "row", "retained earnings, opening group equity", "-retained",
                [("retained", "prior-year retained earnings", *pr["3200"])], -pr["3200"][0]),
        _record("row:3300", "row", "closing translation reserve", "-(opening + movement)",
                [("opening", "prior-year reserve", *pr["3300"]),
                 ("movement", "reserve movement", res.movement_balance, "calc:fig:translation_reserve_movement")],
                -res.closing),
        _record("row:3400", "row", "NCI before this year's profit", "-(opening + at_acquisition + translation)",
                [("opening", "prior-year NCI", *pr["3400"]),
                 ("at_acquisition", "NCI at completion", acq.nci_at_acquisition, acq_refs),
                 ("translation", "NCI translation difference", acq.nci_translation, acq_refs)],
                -(pr["3400"][0] + acq.nci_at_acquisition + acq.nci_translation)),
    ]


def _accounts(run: "Consolidation", **match: str) -> list[str]:
    coa = run.ctx.inputs.coa
    return sorted(a for a in run.balances if a in coa and all(getattr(coa[a], k) == v for k, v in match.items()))


def _sum_figure(run: "Consolidation", key: str, label: str, accounts: list[str], negate: bool) -> CalcRecord:
    terms = [(f"a{i + 1}", f"balance of {a}", run.balances[a], f"calc:row:{a}") for i, a in enumerate(accounts)]
    body = " + ".join(t[0] for t in terms) or "0"
    return _record(f"fig:{key}", "figure", label, f"-({body})" if negate else body, terms,
                   _value(run.figures[key]))


def _india_sources(run: "Consolidation", statement: str) -> str:
    coa = run.ctx.inputs.coa
    return _refs([s for p in run.local if p.entity == "IN" and p.account in coa
                  and coa[p.account].statement == statement for s in p.sources])


def _acquisition_figures(run: "Consolidation", fx: FxTable) -> list[CalcRecord]:
    inputs, acq, res = run.ctx.inputs, run.acquisition, run.reserve
    assert acq is not None and res is not None
    note, prior_nci = inputs.acquisition, inputs.prior_equity["3400"]
    ref = {k: str(v) for k, v in note.refs.items()}
    interest = ("interest", "interest acquired, %", note.interest_pct, ref["interest"])
    close = ("closing_rate", "INR per GBP at closing", acq.closing_rate, fx.ref("INR", "closing"))
    return [
        _record("fig:goodwill_closing", "figure", "goodwill in GBP (policy 4)",
                "(consideration - interest / 100 * net_assets) / closing_rate",
                [("consideration", "consideration, INR", note.consideration_inr, ref["consideration"]), interest,
                 ("net_assets", "net assets at completion, INR", note.net_assets_at_completion, ref["net_assets"]),
                 close], acq.goodwill_gbp),
        _record("fig:profit_nci", "figure", "NCI share of India profit", "(1 - interest / 100) * profit",
                [interest, ("profit", "India profit for the months owned, GBP", acq.india_profit_gbp,
                            _india_sources(run, "PL"))], acq.nci_profit),
        _record("fig:nci_closing", "figure", "closing NCI",
                "opening + (1 - interest / 100) * net_assets / closing_rate",
                [("opening", "prior-year NCI", prior_nci.amount_gbp, str(prior_nci.ref)), interest,
                 ("net_assets", "India net assets, INR", acq.india_net_assets_inr, _india_sources(run, "BS")), close],
                res.nci_closing),
    ]


def _reserve_figures(run: "Consolidation") -> list[CalcRecord]:
    prior, res, acq = run.ctx.inputs.prior_equity, run.reserve, run.acquisition
    assert res is not None and acq is not None
    p = {k: (v.amount_gbp, str(v.ref)) for k, v in prior.items()}
    return [
        _record("fig:profit_owners", "figure", "profit attributable to owners", "group_profit - nci_profit",
                [("group_profit", "group profit", _value(run.figures["group_profit"]), "calc:fig:group_profit"),
                 ("nci_profit", "NCI profit", acq.nci_profit, "calc:fig:profit_nci")], res.owners_profit),
        _record("fig:translation_reserve_movement", "figure", "movement on the translation reserve (policy 2)",
                "net_assets - capital - (retained_open + owners_profit) - nci_closing - reserve_open",
                [("net_assets", "group net assets", _value(run.figures["total_equity"]), "calc:fig:total_equity"),
                 ("capital", "prior-year share capital", *p["3100"]),
                 ("retained_open", "prior-year retained earnings", *p["3200"]),
                 ("owners_profit", "profit attributable to owners", res.owners_profit, "calc:fig:profit_owners"),
                 ("nci_closing", "closing NCI", res.nci_closing, "calc:fig:nci_closing"),
                 ("reserve_open", "prior-year reserve", *p["3300"])], res.movement_balance),
    ]


def _other_figures(run: "Consolidation", fx: FxTable) -> list[CalcRecord]:
    ic, out = run.ic, []
    if ic is not None and ic.difference is not None:
        transit = _refs([i.ref for i in ic.in_transit]) if ic.in_transit else "intercompany.csv"
        out.append(_record("fig:intercompany_difference", "figure", "intercompany difference (policy 5)",
                           "in_transit + revaluation",
                           [("in_transit", "invoice not yet booked by the receiver", ic.causes["in_transit"], transit),
                            ("revaluation", "matched invoices against what the receiver booked",
                             ic.causes["revaluation"], "intercompany.csv")], ic.difference))
    lines = [ln for ln in run.ctx.inputs.trial_balances.get("UK", []) if ln.txn_ccy == "SGD"]
    restated = [restated_amount(ln, fx) for ln in lines]
    if lines and all(a is not None for a in restated):
        terms = [(f"s{i + 1}", f"{ln.local_code} SGD {ln.txn_amount} at closing", a, str(ln.ref))
                 for i, (ln, a) in enumerate(zip(lines, restated, strict=True)) if a is not None]
        out.append(_record("fig:sgd_bank_gbp", "figure", "UK SGD bank at the closing rate",
                           " + ".join(t[0] for t in terms), terms, sum((t[2] for t in terms), Decimal(0))))
    counts = {s: Decimal(sum(1 for d in run.dispositions if d.status == s)) for s in ("POST", "REJECT", "HOLD")}
    out.append(_record("fig:journals", "figure", "journals read = posted + rejected + held",
                       "posted + rejected + held",
                       [("posted", "posted", counts["POST"], "adjustments.json"),
                        ("rejected", "rejected", counts["REJECT"], "adjustments.json"),
                        ("held", "held", counts["HOLD"], "adjustments.json")], Decimal(len(run.dispositions))))
    return out


def calculation_records(run: "Consolidation") -> list[CalcRecord]:
    """Empty when the run is blocked: there is nothing computed to explain."""
    if run.blocked is not None or run.reserve is None or run.acquisition is None:
        return []
    fx = FxTable(run.ctx.inputs.rates)
    figures = [
        _sum_figure(run, "group_revenue", "group revenue", _accounts(run, account_type="Revenue"), True),
        _sum_figure(run, "group_profit", "group profit", _accounts(run, statement="PL"), True),
        _sum_figure(run, "total_assets", "total assets", _accounts(run, account_type="Asset"), False),
        _sum_figure(run, "total_equity", "total equity = net assets", _accounts(run, statement="BS"), False),
    ]
    return (_row_records(run) + _equity_rows(run) + figures + _acquisition_figures(run, fx)
            + _reserve_figures(run) + _other_figures(run, fx))
