from decimal import Decimal

from app.core.post_journals import decide, import_postings, journal_postings
from app.detectors.mapping import classified
from app.detectors.registry import run_all
from app.domain.journals import Disposition
from app.domain.runs import Context
from app.parsers.mappings import apply_mapping


def dispositions(ctx: Context, assumptions: dict[str, bool | str] | None = None) -> list[Disposition]:
    use = ctx.assumptions if assumptions is None else assumptions
    return decide(ctx.inputs.journals, run_all(ctx), use)


def ids(result: list[Disposition], status: str) -> list[str]:
    return [d.journal_id for d in result if d.status == status]


def test_fifteen_posted_three_rejected_two_held(ctx: Context) -> None:
    result = dispositions(ctx)
    assert ids(result, "POST") == [
        "JE-001", "JE-002", "JE-003", "JE-004", "JE-005", "JE-007", "JE-008", "JE-010",
        "JE-011", "JE-012", "JE-013", "JE-014", "JE-015", "JE-018", "JE-020",
    ]
    assert ids(result, "REJECT") == ["JE-006", "JE-017", "JE-019"]
    assert ids(result, "HOLD") == ["JE-009", "JE-016"]


def test_every_rejected_or_held_journal_has_a_reason(ctx: Context) -> None:
    for item in dispositions(ctx):
        assert (item.status == "POST") == (item.reasons == ())


def test_je006_is_rejected_because_it_is_unbalanced_not_because_of_its_memo(ctx: Context) -> None:
    je6 = next(d for d in dispositions(ctx) if d.journal_id == "JE-006")
    assert je6.status == "REJECT" and je6.reasons[0].startswith("D03 unbalanced")
    assert all("PRE-APPROVED" not in r.upper() and "AUTOMATED" not in r.upper() for r in je6.reasons)


def test_posting_the_je017_assumption_posts_it(ctx: Context) -> None:
    assert "JE-017" in ids(dispositions(ctx, {**ctx.assumptions, "je017": "post"}), "POST")


def test_if_the_journals_are_already_in_the_trial_balances_none_is_posted(ctx: Context) -> None:
    result = dispositions(ctx, {**ctx.assumptions, "journals_in_tb": True})
    assert ids(result, "POST") == []


def test_held_journals_post_only_when_that_assumption_is_switched_on(ctx: Context) -> None:
    result = dispositions(ctx, {**ctx.assumptions, "held_journals_posted": True})
    assert {"JE-009", "JE-016"} <= set(ids(result, "POST"))


def test_uk_rent_journal_posts_to_group_6200_not_to_finance_costs(ctx: Context) -> None:
    postings = journal_postings(ctx.inputs, ctx.inputs.journals, dispositions(ctx))
    je10 = [p for p in postings if p.note.startswith("JE-010")]
    assert {(p.account, p.amount) for p in je10} == {("1400", Decimal("26000.00")), ("6200", Decimal("-26000.00"))}


def test_uk_debtors_code_1100_posts_to_receivables_not_cash(ctx: Context) -> None:
    postings = journal_postings(ctx.inputs, ctx.inputs.journals, dispositions(ctx))
    assert ("1200", Decimal("-9400.00")) in {(p.account, p.amount) for p in postings if p.note.startswith("JE-011")}


def test_each_posted_journal_nets_to_zero(ctx: Context) -> None:
    postings = journal_postings(ctx.inputs, ctx.inputs.journals, dispositions(ctx))
    for je in {p.note.split()[0] for p in postings}:
        assert sum((p.amount for p in postings if p.note.startswith(je)), Decimal(0)) == 0


def test_journal_postings_carry_the_source_line_of_the_journal(ctx: Context) -> None:
    postings = journal_postings(ctx.inputs, ctx.inputs.journals, dispositions(ctx))
    assert str(postings[0].sources[0]) == "adjustments.json:14"


def test_import_keeps_every_trial_balance_line_and_flags_the_remap(ctx: Context) -> None:
    mapped = apply_mapping(classified(ctx), ctx.assumptions)
    postings = import_postings(mapped)
    assert len(postings) == sum(len(lines) for lines in ctx.inputs.trial_balances.values())
    deferred = next(p for p in postings if p.note.startswith("2310"))
    assert deferred.account == "2300" and "remapped" in deferred.note and len(deferred.sources) == 2
