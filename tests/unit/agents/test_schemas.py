import pytest
from pydantic import ValidationError

from app.agents.journal_reviewer.schema import JournalVerdict
from app.agents.mapping_reviewer.schema import mapping_verdict_model
from app.domain.runs import Context

NONE_SET = dict.fromkeys(JournalVerdict.CATEGORIES, False)


def test_risk_is_worked_out_from_the_booleans_and_cannot_be_stated() -> None:
    assert JournalVerdict(reason="ok", **NONE_SET).risk is False
    verdict = JournalVerdict(reason="x", **{**NONE_SET, "unbalanced": True})
    assert verdict.risk and verdict.flags == ("unbalanced",)
    assert "risk" not in JournalVerdict.model_fields


def test_every_category_is_a_required_boolean() -> None:
    with pytest.raises(ValidationError):
        JournalVerdict(reason="x", unbalanced=True)  # type: ignore[call-arg]
    assert all(JournalVerdict.model_fields[c].annotation is bool for c in JournalVerdict.CATEGORIES)


def test_the_mapping_schema_allows_only_accounts_in_the_chart(ctx: Context) -> None:
    model = mapping_verdict_model(tuple(sorted(ctx.inputs.coa)))
    flags = {"name_mismatch": True, "wrong_statement_type": False, "sign_unusual": False, "reason": "x"}
    assert model(**flags, better_group_code="2300").better_group_code == "2300"  # type: ignore[call-arg]
    assert model(**flags).better_group_code == "none"
    with pytest.raises(ValidationError):
        model(**flags, better_group_code="9999")  # type: ignore[call-arg]
    allowed = model.model_json_schema()["properties"]["better_group_code"]["enum"]
    assert sorted(allowed) == sorted(["none", *ctx.inputs.coa])
