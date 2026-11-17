import tomllib

from app.parsers.policy_text import compare, read_policy
from app.utils.paths import CONFIG_DIR, DEFAULT_DATA_DIR

TEXT = (DEFAULT_DATA_DIR / "group_policies.md").read_text(encoding="utf-8")
APPROVED = tomllib.loads((CONFIG_DIR / "policy.toml").read_text(encoding="utf-8"))


def reading(text: str, field: str):  # type: ignore[no-untyped-def]
    return next(r for r in read_policy(text) if r.field == field)


def test_the_supplied_clauses_are_all_read_and_agree_with_the_approved_policy() -> None:
    readings = read_policy(TEXT)
    assert len(readings) == 8 and all(r.value is not None for r in readings)
    assert compare(readings, APPROVED) == []


def test_each_reading_cites_its_clause_and_the_sentence_it_came_from() -> None:
    r = reading(TEXT, "foreign_currency_items.monetary_items")
    assert r.clause == 3 and "retranslated at the closing rate" in r.quote and r.reader == "LEXICON"


def test_a_reworded_clause_is_still_read() -> None:
    reworded = TEXT.replace("Assets and liabilities: closing rate at 31 December 2024.",
                            "Assets and liabilities: translated at the year-end rate.")
    assert reading(reworded, "translation.assets_liabilities").value == "closing"
    assert compare(read_policy(reworded), APPROVED) == []


def test_a_clause_that_now_says_something_else_is_reported_as_a_difference() -> None:
    changed = TEXT.replace("Assets and liabilities: closing rate at 31 December 2024.",
                           "Assets and liabilities: average rate for the year.")
    assert compare(read_policy(changed), APPROVED) == [
        ("translation.assets_liabilities", "clause 2 reads average; policy.toml says closing")]


def test_an_unreadable_clause_gives_unknown_not_a_guess() -> None:
    vague = TEXT.replace("Assets and liabilities: closing rate at 31 December 2024.",
                         "Assets and liabilities: as set out in Annex B.")
    r = reading(vague, "translation.assets_liabilities")
    assert r.value is None and "no wording" in r.reason
    assert compare(read_policy(vague), APPROVED)[0][1].startswith("unreadable")


def test_a_sentence_that_matches_two_choices_is_ambiguous() -> None:
    both = TEXT.replace("Assets and liabilities: closing rate at 31 December 2024.",
                        "Assets and liabilities: closing rate, or the average rate if easier.")
    assert reading(both, "translation.assets_liabilities").value is None
    assert "ambiguous" in reading(both, "translation.assets_liabilities").reason


def test_a_missing_clause_gives_unknown() -> None:
    assert reading(TEXT.split("6. **Journals.**")[0], "journals.posting_rule").value is None
