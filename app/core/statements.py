"""Consolidated balances, and the balance sheet, profit and loss and changes in equity built from them."""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.domain.entries import Entry, Posting
from app.domain.ledger import CoaAccount

Coa = dict[str, CoaAccount]
Balances = dict[str, Decimal]


def balances_by_account(translated: list[Posting], eliminations: list[Entry], coa: Coa) -> Balances:
    """Debit-positive GBP balance per group account. Equity legs of eliminations are left out: consolidated equity is
    built from the prior-year file and the reserve, not from translating each entity's own equity."""
    totals: Balances = {}
    legs = list(translated) + [leg for entry in eliminations for leg in entry.lines]
    for p in legs:
        account = coa.get(p.account)
        if account is not None and account.account_type == "Equity":
            continue
        totals[p.account] = totals.get(p.account, Decimal(0)) + p.amount
    return totals


def _sum(balances: Balances, coa: Coa, **match: str) -> Decimal:
    keep = (v for k, v in balances.items() if k in coa and all(getattr(coa[k], f) == w for f, w in match.items()))
    return sum(keep, Decimal(0))


def net_assets(balances: Balances, coa: Coa) -> Decimal:
    """Assets less liabilities: the debit-positive sum of the balance-sheet accounts. Equal to total equity."""
    return _sum(balances, coa, statement="BS")


def profit(balances: Balances, coa: Coa) -> Decimal:
    """Group profit for the year: the credit balance of the income-statement accounts."""
    return -_sum(balances, coa, statement="PL")


def revenue(balances: Balances, coa: Coa) -> Decimal:
    return -_sum(balances, coa, account_type="Revenue")


def total_assets(balances: Balances, coa: Coa) -> Decimal:
    return _sum(balances, coa, account_type="Asset")


@dataclass(frozen=True)
class EquityView:
    """The equity side as numbers: opening, the year's movements, closing. NCI profit is shown inside NCI."""

    share_capital: Decimal
    retained_opening: Decimal
    reserve_opening: Decimal
    nci_opening: Decimal
    owners_profit: Decimal
    nci_acquired: Decimal
    nci_profit: Decimal
    nci_translation: Decimal
    reserve_movement: Decimal

    def retained_closing(self) -> Decimal:
        return self.retained_opening + self.owners_profit

    def reserve_closing(self) -> Decimal:
        return self.reserve_opening + self.reserve_movement

    def nci_closing(self) -> Decimal:
        return self.nci_opening + self.nci_acquired + self.nci_profit + self.nci_translation

    def total(self) -> Decimal:
        return self.share_capital + self.retained_closing() + self.reserve_closing() + self.nci_closing()


def _lines(balances: Balances, coa: Coa, kind: str, sign: int) -> list[tuple[str, str, Decimal]]:
    return [(c, coa[c].name, sign * balances[c]) for c in sorted(balances)
            if c in coa and coa[c].account_type == kind and balances[c] != 0]


def _rows(lines: list[tuple[str, str, Decimal]]) -> list[dict[str, object]]:
    return [{"account": c, "name": n, "amount_gbp": v} for c, n, v in lines]


def balance_sheet(balances: Balances, coa: Coa, equity: EquityView, as_of: date) -> dict[str, object]:
    assets, liabilities = _lines(balances, coa, "Asset", 1), _lines(balances, coa, "Liability", -1)
    equity_lines = [("3100", "Share capital", equity.share_capital),
                    ("3200", "Retained earnings", equity.retained_closing()),
                    ("3300", "Translation reserve", equity.reserve_closing()),
                    ("3400", "Non-controlling interest", equity.nci_closing())]
    return {
        "currency": "GBP", "as_of": as_of.isoformat(),
        "assets": _rows(assets), "total_assets": sum((v for _, _, v in assets), Decimal(0)),
        "liabilities": _rows(liabilities), "total_liabilities": sum((v for _, _, v in liabilities), Decimal(0)),
        "equity": _rows(equity_lines), "total_equity": equity.total(),
    }


def profit_and_loss(
    balances: Balances, coa: Coa, period: tuple[date, date], split: tuple[Decimal, Decimal],
) -> dict[str, object]:
    income, costs = _lines(balances, coa, "Revenue", -1), _lines(balances, coa, "Expense", 1)
    return {
        "currency": "GBP", "period": f"{period[0].isoformat()} to {period[1].isoformat()}",
        "revenue": _rows(income), "total_revenue": sum((v for _, _, v in income), Decimal(0)),
        "expenses": _rows(costs), "total_expenses": sum((v for _, _, v in costs), Decimal(0)),
        "profit_for_the_year": profit(balances, coa),
        "attributable_to": {"owners_of_the_parent": split[0], "non_controlling_interest": split[1]},
    }


def changes_in_equity(e: EquityView, period: tuple[date, date]) -> dict[str, object]:
    zero = Decimal(0)
    table = [
        ("Opening balance", e.share_capital, e.retained_opening, e.reserve_opening, e.nci_opening),
        ("Profit for the year", zero, e.owners_profit, zero, e.nci_profit),
        ("Non-controlling interest on acquisition of Northwind India", zero, zero, zero, e.nci_acquired),
        ("Exchange differences on translation", zero, zero, e.reserve_movement, e.nci_translation),
    ]
    table.append(("Closing balance", *(sum((row[i] for row in table), zero) for i in range(1, 5))))  # type: ignore[arg-type]
    rows = [{"item": label, "share_capital": sc, "retained_earnings": re, "translation_reserve": tr,
             "non_controlling_interest": nci, "total": sc + re + tr + nci} for label, sc, re, tr, nci in table]
    return {"currency": "GBP", "period": f"{period[0].isoformat()} to {period[1].isoformat()}", "rows": rows}
