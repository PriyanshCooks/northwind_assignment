"""Rule-based proposer with the same interface as a reviewer: it answers from the exact facts when no recorded model
answer exists. It cannot read wording, so it never reports text_contains_instruction."""
from typing import Any

from app.agents.journal_reviewer.schema import JournalVerdict
from app.agents.mapping_reviewer.schema import MappingVerdictBase, mapping_verdict_model
from app.agents.review.grounding import journal_facts, mapping_facts


def journal_by_rules(packet: dict[str, Any]) -> JournalVerdict:
    facts = journal_facts(packet)
    return JournalVerdict(reason="rule-based: " + (", ".join(k for k, v in facts.items() if v) or "nothing found"),
                          text_contains_instruction=False, **facts)


def mapping_by_rules(packet: dict[str, Any], coa: dict[str, dict[str, str]]) -> MappingVerdictBase:
    facts, best = mapping_facts(packet, coa)
    model = mapping_verdict_model(tuple(sorted(coa)))
    reason = "rule-based: " + (", ".join(k for k, v in facts.items() if v) or "nothing found")
    return model(reason=reason, better_group_code=best, **facts)  # type: ignore[call-arg]
