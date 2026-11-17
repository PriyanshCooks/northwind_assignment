"""Issue cards say what the data says, in plain words, and never claim an AI view that was not recorded."""
from typing import Any

from fastapi.testclient import TestClient

from app.services.cards_service import plain
from tests.api.conftest import finished_run


def _cards(client: TestClient) -> dict[str, dict[str, Any]]:
    run_id = finished_run(client)
    cards = client.get(f"/api/runs/{run_id}/review").json()["cards"]
    return {c["headline"]: c for c in cards}


def test_amounts_get_separators_and_lose_empty_cents() -> None:
    assert plain("debits 51200.00, credits 50000.00") == "debits 51,200, credits 50,000"
    assert plain("booked 23010.55 on 2024-12-31 at rate 1.2650") == "booked 23,010.55 on 2024-12-31 at rate 1.2650"


def test_je006_card_names_the_imbalance_and_the_memo_as_data(client: TestClient) -> None:
    card = next(c for h, c in _cards(client).items() if h.startswith("JE-006 does not balance"))
    assert "debits 51,200, credits 50,000" in card["headline"]
    assert "asks reviewers to skip the check and is treated as data" in card["headline"]
    assert card["evidence"] == {"file": "adjustments.json", "line": 102}
    assert "rejected and not posted" in card["rules"]


def test_the_memo_card_quotes_the_text_and_the_ai_line_never_says_agrees_without_a_record(client: TestClient) -> None:
    cards = _cards(client).values()
    memo = next(c for c in cards if c["code"] == "D12")
    assert "AUTOMATED REVIEWERS" in memo["quote"] and memo["ai"]["state"] == "not_reviewed"
    assert all(c["ai"]["state"] in {"agrees", "disagrees", "no_claim", "not_reviewed"} for c in cards)


def test_the_disagreeing_journal_says_what_the_model_missed(client: TestClient) -> None:
    card = next(c for h, c in _cards(client).items() if h.startswith("JE-009"))
    assert card["ai"]["state"] == "disagrees" and "exceeds_balance" in card["ai"]["text"]


def test_results_carry_the_same_cards_without_buttons(client: TestClient) -> None:
    run_id = finished_run(client)
    cards = client.get(f"/api/runs/{run_id}/results").json()["cards"]
    assert cards and all(c["actions"] == [] for c in cards)


def test_the_review_carries_the_recorded_review_totals_and_every_unit(client: TestClient) -> None:
    run_id = finished_run(client)
    ai = client.get(f"/api/runs/{run_id}/review").json()["ai"]
    assert ai["label"] == "recorded review" and ai["totals"]["units"] == len(ai["units"]) == 63
    unchecked = sum(len(u["unverified"]) for u in ai["units"])
    assert ai["totals"]["claims"] == ai["totals"]["verified"] + ai["totals"]["dropped"] + unchecked
    je006 = next(u for u in ai["units"] if u["unit"] == "JE-006")
    assert je006["packet"]["total_debit"] == "51200.00" and je006["answer"]["unbalanced"] is True


def test_build_lists_the_stages_the_run_really_logged(client: TestClient) -> None:
    run_id = finished_run(client)
    stages = client.post(f"/api/runs/{run_id}/build").json()["stages"]
    assert [s["stage"] for s in stages][:2] == ["intake", "analyse"] and "export" in {s["stage"] for s in stages}
    assert all("data_dir" not in s and "folder" not in s for s in stages)
