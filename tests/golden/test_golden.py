"""The Wave 1 gate: every control figure equals the hand calculation, or the difference is explained here."""
import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.domain.figures import Determined, Provisional, Unknown
from app.domain.runs import Context
from app.services.run_service import Consolidation, stage

GOLDEN = json.loads(Path(__file__).with_name("handcalc.json").read_text(encoding="utf-8"))
TOLERANCE = Decimal(GOLDEN["tolerance"])

# Status differences, all deliberate and explained in the WORKLOG (task 1.10): the hand calculation calls these
# figures determined, the engine calls them provisional because the unrevalued UK SGD bank would move each of them
# through 7300 once a GBP/SGD closing rate exists. The values are identical.
STATUS_DIFFERS = {"group_profit", "profit_owners", "total_equity"}


@pytest.fixture(scope="module")
def run(ctx: Context) -> Consolidation:
    return stage(ctx)


@pytest.mark.parametrize("key", [k for k in GOLDEN["figures"] if k not in {"sgd_bank_gbp", "journals"}])
def test_number_matches_the_hand_calculation(run: Consolidation, key: str) -> None:
    figure = run.figures[key]
    assert isinstance(figure, (Determined, Provisional)) and isinstance(figure.value, Decimal)
    assert abs(figure.value - Decimal(GOLDEN["figures"][key]["value"])) <= TOLERANCE


def test_sgd_bank_is_unknown_in_both(run: Consolidation) -> None:
    assert isinstance(run.figures["sgd_bank_gbp"], Unknown) and GOLDEN["figures"]["sgd_bank_gbp"]["value"] is None


def test_journal_counts_and_ids_match(run: Consolidation) -> None:
    figure = run.figures["journals"]
    assert isinstance(figure, Determined) and figure.value == GOLDEN["figures"]["journals"]["value"]
    by_status = {s: [d.journal_id for d in run.dispositions if d.status == s] for s in ("POST", "REJECT", "HOLD")}
    assert by_status == {"POST": GOLDEN["journals_by_id"]["posted"], "REJECT": GOLDEN["journals_by_id"]["rejected"],
                         "HOLD": GOLDEN["journals_by_id"]["held"]}


def test_statuses_match_except_the_explained_differences(run: Consolidation) -> None:
    differs = set()
    for key, expected in GOLDEN["figures"].items():
        actual = run.figures[key]
        kind = "unknown" if isinstance(actual, Unknown) else actual.kind
        if kind != expected["status"]:
            differs.add(key)
    assert differs == STATUS_DIFFERS


def test_intercompany_causes_match(run: Consolidation) -> None:
    assert run.ic is not None
    causes = {k: round(v, 2) for k, v in run.ic.causes.items()}
    assert causes == {"in_transit": Decimal(GOLDEN["intercompany_causes"]["in_transit"]),
                      "revaluation": Decimal(GOLDEN["intercompany_causes"]["revaluation"])}


def test_rate_residual_to_7300_matches(run: Consolidation) -> None:
    income = next(e for e in run.eliminations if e.id == "ELIM-IC-INCOME")
    residual = next(p.amount for p in income.lines if p.account == "7300")
    assert abs(-residual - Decimal(GOLDEN["intercompany_causes"]["income_expense_rate_residual_to_7300"])) <= TOLERANCE


def test_reserve_components_match(run: Consolidation) -> None:
    assert run.reserve is not None
    for key, value in GOLDEN["reserve_components"].items():
        assert abs(run.reserve.components[key] - Decimal(value)) <= TOLERANCE, key
