"""The golden file lists the 12 brief keys and is honest about being provisional."""
import json
from pathlib import Path

GOLDEN = Path(__file__).with_name("handcalc.json")
BRIEF_KEYS = {
    "group_revenue", "group_profit", "profit_owners", "profit_nci", "nci_closing", "goodwill_closing",
    "translation_reserve_movement", "total_assets", "total_equity", "intercompany_difference",
    "sgd_bank_gbp", "journals",
}


def load() -> dict:
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


def test_golden_file_has_exactly_the_twelve_brief_keys() -> None:
    assert set(load()["figures"]) == BRIEF_KEYS


def test_golden_file_is_marked_unreviewed() -> None:
    assert load()["review_status"].startswith("provisional")


def test_unknown_figure_carries_a_reason_and_no_value() -> None:
    sgd = load()["figures"]["sgd_bank_gbp"]
    assert sgd["value"] is None and sgd["reason"]


def test_journal_ids_add_up_to_the_counts() -> None:
    golden = load()
    counts = golden["figures"]["journals"]["value"]
    by_id = golden["journals_by_id"]
    assert {status: len(ids) for status, ids in by_id.items()} == counts
