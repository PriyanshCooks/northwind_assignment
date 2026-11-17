"""Reads entities.csv, subledger_controls.csv, prior_year_group.csv and intercompany.csv."""
from datetime import date
from pathlib import Path

from app.domain.runs import Entity, IcInvoice, PriorEquity, SubledgerControl
from app.parsers.contracts import Contract, check_percentage, read_rows
from app.utils.money import to_decimal

ENTITIES = Contract(
    ("entity_id", "legal_name", "country", "functional_currency", "ownership_pct", "acquisition_date",
     "financial_year_end", "erp_system", "tb_file"),
)
SUBLEDGER = Contract(
    ("entity_id", "ledger", "currency", "control_total", "as_of"), decimals=("control_total",), dates=("as_of",),
)
PRIOR = Contract(
    ("group_account", "account_name", "amount_gbp", "as_of", "note"), decimals=("amount_gbp",), dates=("as_of",),
)
INTERCOMPANY = Contract(
    ("reporting_entity", "counterparty", "doc_ref", "doc_date", "doc_currency", "doc_amount",
     "booked_currency", "booked_amount", "description"),
    decimals=("doc_amount", "booked_amount"), dates=("doc_date",),
)


def load_entities(path: Path) -> dict[str, Entity]:
    entities = {}
    for row in read_rows(path, ENTITIES):
        v = row.values
        if v["ownership_pct"]:
            check_percentage(path.name, row.line, "ownership_pct", v["ownership_pct"])
        entities[v["entity_id"]] = Entity(
            ref=row.ref, id=v["entity_id"], currency=v["functional_currency"],
            ownership_pct=to_decimal(v["ownership_pct"]) if v["ownership_pct"] else None,
            acquisition_date=date.fromisoformat(v["acquisition_date"]) if v["acquisition_date"] else None,
            tb_file=v["tb_file"],
        )
    return entities


def load_subledger(path: Path) -> list[SubledgerControl]:
    return [
        SubledgerControl(
            ref=r.ref, entity=r.values["entity_id"], ledger=r.values["ledger"], currency=r.values["currency"],
            control_total=to_decimal(r.values["control_total"]),
        )
        for r in read_rows(path, SUBLEDGER)
    ]


def load_prior_equity(path: Path) -> dict[str, PriorEquity]:
    rows = read_rows(path, PRIOR)
    return {
        r.values["group_account"]: PriorEquity(
            ref=r.ref, account=r.values["group_account"], amount_gbp=to_decimal(r.values["amount_gbp"]),
        )
        for r in rows
    }


def load_intercompany(path: Path) -> list[IcInvoice]:
    return [
        IcInvoice(
            ref=r.ref, reporting_entity=r.values["reporting_entity"], counterparty=r.values["counterparty"],
            doc_ref=r.values["doc_ref"], doc_date=date.fromisoformat(r.values["doc_date"]),
            doc_currency=r.values["doc_currency"], doc_amount=to_decimal(r.values["doc_amount"]),
            booked_currency=r.values["booked_currency"], booked_amount=to_decimal(r.values["booked_amount"]),
        )
        for r in read_rows(path, INTERCOMPANY)
    ]
