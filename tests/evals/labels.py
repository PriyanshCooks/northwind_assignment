"""Hand labels for the supplied data: which categories are really true for each unit. Worked out from the findings and
the files, not from the reviewers. Every unit not listed here is clean."""

JOURNALS = {
    "JE-006": {"unbalanced", "text_contains_instruction"},
    "JE-009": {"exceeds_balance"},
    "JE-014": {"duplicate_of_another"},
    "JE-019": {"duplicate_of_another"},
    "JE-016": {"account_not_in_chart"},
    "JE-017": {"outside_period"},
}
MAPPINGS = {"UK:2310:12": {"name_mismatch", "wrong_statement_type"}}


def expected(unit_id: str, kind: str) -> set[str]:
    return set((JOURNALS if kind == "journal" else MAPPINGS).get(unit_id, set()))
