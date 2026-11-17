"""A second implementation of the same method, recomputing the control figures from the raw files.

It shares the policy and the assumptions (A1, A3, A6, A9, and the 2310 remap switch passed in by the run), so it is not
an independent check of the accounting. It imports nothing from app.core or app.parsers (only the figure names and
the invariants): it reads the files itself, works entity by entity in local
currency, and translates once at the end. A disagreement with the pipeline is reported, never adjusted away."""
import csv
import json
import re
from decimal import Decimal as D
from pathlib import Path
from typing import Any

from app.domain.figures import Determined, Figure, Provisional, Unknown
from app.verification.invariants import Check

NUMERIC = ("group_revenue", "group_profit", "profit_owners", "profit_nci", "nci_closing", "goodwill_closing",
           "translation_reserve_movement", "total_assets", "total_equity", "intercompany_difference")
Books = dict[str, D]


def _rows(path: Path) -> list[dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


class Rates:
    def __init__(self, path: Path) -> None:
        self.value: dict[tuple[str, str, str], D] = {}
        self.window: dict[str, str] = {}
        for r in _rows(path):
            units = r["convention"].split(" per 1 ")[0]
            rate = D(r["rate"]) if units == r["quote_currency"] else 1 / D(r["rate"])
            self.value[(r["base_currency"], r["quote_currency"], r["rate_type"])] = rate
            self.window[r["as_of"]] = r["rate_type"]

    def per_gbp(self, ccy: str, kind: str) -> D:
        usd = self.value[("GBP", "USD", kind)]
        return usd if ccy == "USD" else usd * self.value[("USD", ccy, kind)]


def _add(books: Books, code: str, amount: D) -> None:
    books[code] = books.get(code, D(0)) + amount


def _plus(books: Books, coa: dict[str, dict[str, str]], **match: str) -> D:
    return sum((v for k, v in books.items() if all(coa[k][f] == w for f, w in match.items())), D(0))


def _journals(data: Path, known: dict[str, set[str]], opening: dict[tuple[str, str], D],
              side: dict[tuple[str, str], str]) -> tuple[dict[str, str], list[dict[str, Any]]]:
    """posted, rejected or held for each journal, by rules written afresh here."""
    raw: dict[str, Any] = json.loads(
        (data / "adjustments.json").read_text(encoding="utf-8"), parse_float=str, parse_int=str)
    seen: set[tuple[object, ...]] = set()
    status: dict[str, str] = {}
    balance = dict(opening)
    for e in raw["entries"]:
        lines = [(x["account"], D(x["debit"]), D(x["credit"])) for x in e["lines"]]
        key = (e["entity"], e["date"], tuple(sorted(lines)))
        repeat, unknown, flips = key in seen, any(a not in known[e["entity"]] for a, _, _ in lines), False
        seen.add(key)
        for account, dr, cr in ([] if unknown else lines):
            before = balance.get((e["entity"], account), D(0))
            balance[(e["entity"], account)] = before + dr - cr
            now, normal = before + dr - cr, side.get((e["entity"], account))
            flips = flips or (normal == "Credit" and before <= 0 < now) or (normal == "Debit" and before >= 0 > now)
        bad = sum(x[1] for x in lines) != sum(x[2] for x in lines) or not e["date"].startswith("2024") or repeat
        status[e["id"]] = "rejected" if bad else "held" if unknown or flips else "posted"
    return status, raw["entries"]


def recompute(data: Path, remap_deferred_income: bool = True) -> dict[str, object]:
    rates = Rates(data / "fx_rates.csv")
    coa = {r["account_code"]: r for r in _rows(data / "group_coa.csv")}
    maps = {e: {r["local_code"]: r["group_code"] for r in _rows(data / f"map_{e}.csv")} for e in ("uk", "in")}
    if remap_deferred_income:
        maps["uk"]["2310"] = "2300"
    ents = {r["entity_id"]: r for r in _rows(data / "entities.csv")}
    note = (data / "acquisition_note.md").read_text(encoding="utf-8")
    consideration = D(re.search(r"Consideration:\*\* INR ([\d,]+)", note).group(1).replace(",", ""))  # type: ignore[union-attr]
    completion_na = D(re.search(r"Net assets at completion\*\* \| \*\*([\d,]+)", note).group(1).replace(",", ""))  # type: ignore[union-attr]
    owned = D(ents["IN"]["ownership_pct"]) / 100
    cutoff = ents["IN"]["acquisition_date"][:7]

    us, uk, ind = Books(), Books(), Books()
    opening: dict[tuple[str, str], D] = {}
    side: dict[tuple[str, str], str] = {}
    for r in _rows(data / "tb_us.csv"):
        amount = D(r["debit"]) - D(r["credit"])
        _add(us, r["account_code"], amount)
        opening[("US", r["account_code"])] = amount
    for r in _rows(data / "tb_uk.csv"):
        _add(uk, maps["uk"][r["nominal_code"]], D(r["balance"]))
        opening[("UK", r["nominal_code"])] = opening.get(("UK", r["nominal_code"]), D(0)) + D(r["balance"])
    for r in _rows(data / "tb_in.csv"):
        amount = D(r["amount"]) * (1 if r["dr_cr"] == "Dr" else -1)
        opening[("IN", r["ledger_code"])] = amount
        if coa[maps["in"][r["ledger_code"]]]["statement"] == "BS":
            _add(ind, maps["in"][r["ledger_code"]], amount)
    for r in _rows(data / "in_pl_monthly.csv"):
        if r["month"] >= cutoff:
            _add(ind, maps["in"][r["ledger_code"]], D(r["amount"]) * (1 if r["dr_cr"] == "Dr" else -1))
    pre_profit = -sum((D(r["amount"]) * (1 if r["dr_cr"] == "Dr" else -1) for r in _rows(data / "in_pl_monthly.csv")
                       if r["month"] < cutoff), D(0))
    _add(ind, "3200", -pre_profit)

    to_group = {"US": {c: c for c in coa}, "UK": maps["uk"], "IN": maps["in"]}
    for (entity, code), _ in opening.items():
        group = to_group[entity].get(code)
        if group and coa[group]["statement"] == "BS":
            side[(entity, code)] = coa[group]["normal_balance"]
    status, entries = _journals(data, {e: set(m) for e, m in to_group.items()}, opening, side)
    for e in entries:
        if status[e["id"]] == "posted":
            books = {"US": us, "UK": uk, "IN": ind}[e["entity"]]
            for x in e["lines"]:
                _add(books, to_group[e["entity"]][x["account"]], D(x["debit"]) - D(x["credit"]))

    close_usd, avg_usd = rates.per_gbp("USD", "closing"), rates.per_gbp("USD", "average")
    close_inr, spot_inr = rates.per_gbp("INR", "closing"), rates.per_gbp("INR", "spot")
    h2_inr = rates.per_gbp("INR", rates.window[f"{ents['IN']['acquisition_date']} to 2024-12-31"])
    payable = next(r for r in _rows(data / "tb_uk.csv") if r["nominal_code"] == "2150")
    revaluation = abs(D(payable["txn_amount"])) / close_usd - abs(D(payable["balance"]))
    invoices = _rows(data / "intercompany.csv")
    uk_refs = {r["doc_ref"] for r in invoices if r["reporting_entity"] == "UK"}
    us_docs = [r for r in invoices if r["reporting_entity"] == "US"]
    transit = sum((D(r["doc_amount"]) for r in us_docs if r["doc_ref"] not in uk_refs), D(0))
    uk_booked = sum((D(r["booked_amount"]) for r in invoices if r["reporting_entity"] == "UK"), D(0))
    ic_difference = sum((D(r["doc_amount"]) for r in us_docs), D(0)) / close_usd - uk_booked
    fixes = revaluation + transit / close_usd

    pl = {name: _plus(books, coa, statement="PL") for name, books in (("US", us), ("UK", uk), ("IN", ind))}
    profit = {"US": -pl["US"] / avg_usd, "UK": -pl["UK"] - fixes, "IN": -pl["IN"] / h2_inr}
    group_profit, nci_profit = sum(profit.values(), D(0)), (1 - owned) * profit["IN"]
    revenue = -us.get("4100", D(0)) / avg_usd - uk.get("4100", D(0)) - ind.get("4100", D(0)) / h2_inr

    goodwill_inr = consideration - owned * completion_na
    inr_na = _plus(ind, coa, statement="BS") - ind.get("3200", D(0)) - ind.get("3100", D(0))
    no_eq = {"statement": "BS"}
    us_na = (_plus(us, coa, **no_eq) - sum(us.get(c, D(0)) for c in ("3100", "3200", "1600", "1610"))) / close_usd
    uk_na = _plus(uk, coa, **no_eq) - sum(uk.get(c, D(0)) for c in ("3100", "3200")) - fixes
    net_assets = us_na + uk_na + inr_na / close_inr + goodwill_inr / close_inr
    us_assets = _plus(us, coa, account_type="Asset") - sum(us.get(c, D(0)) for c in ("1250", "1600", "1610"))
    assets = (us_assets / close_usd + _plus(uk, coa, account_type="Asset")
              + _plus(ind, coa, account_type="Asset") / close_inr + goodwill_inr / close_inr)

    us_open = -(us.get("3100", D(0)) + us.get("3200", D(0)))
    open_usd = rates.per_gbp("USD", "opening")
    spot_usd = rates.per_gbp("USD", "spot")
    movement = (us_open * (1 / close_usd - 1 / open_usd) + (-pl["US"]) * (1 / close_usd - 1 / avg_usd)
                + owned * (completion_na * (1 / close_inr - 1 / spot_inr) + (-pl["IN"]) * (1 / close_inr - 1 / h2_inr))
                + goodwill_inr * (1 / close_inr - 1 / spot_inr)
                - us.get("1600", D(0)) * (1 / close_usd - 1 / open_usd)
                - us.get("1610", D(0)) * (1 / close_usd - 1 / spot_usd))
    return {
        "group_revenue": revenue, "group_profit": group_profit, "profit_owners": group_profit - nci_profit,
        "profit_nci": nci_profit, "nci_closing": (1 - owned) * inr_na / close_inr,
        "goodwill_closing": goodwill_inr / close_inr, "translation_reserve_movement": movement,
        "total_assets": assets, "total_equity": net_assets, "intercompany_difference": ic_difference,
        "journals": {s: sum(1 for v in status.values() if v == s) for s in ("posted", "rejected", "held")},
    }


def oracle_checks(data: Path, figures: dict[str, Figure], tolerance: D, remap: bool = True) -> list[Check]:
    """One check per figure: the pipeline and the oracle must agree within the tolerance (assumption A12)."""
    expected = recompute(data, remap)
    out = []
    for key in NUMERIC:
        figure = figures[key]
        if isinstance(figure, Unknown):
            out.append(Check(f"oracle: {key}", False, f"pipeline says unknown: {figure.reason}"))
            continue
        assert isinstance(figure, (Determined, Provisional)) and isinstance(figure.value, D)
        gap = figure.value - expected[key]  # type: ignore[operator]
        out.append(Check(f"oracle: {key}", abs(gap) <= tolerance, f"pipeline minus oracle = {gap}"))
    counts = figures["journals"]
    same = isinstance(counts, (Determined, Provisional)) and counts.value == expected["journals"]
    out.append(Check("oracle: journals", same, str(expected["journals"])))
    return out
