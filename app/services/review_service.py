"""Run the two reviewers over every unit: replay or record the model answer, ground each claim, and fall back to the
rule-based proposer when no usable answer exists. The result is advice (policy 2): it never changes a figure."""
from dataclasses import dataclass

from app.agents.journal_reviewer.llm_model import review_journal
from app.agents.mapping_reviewer.llm_model import review_mapping
from app.domain.runs import Context
from app.llm.client import Mode
from app.llm.factory import LlmConfig
from app.llm.ledger import Ledger, LlmUnavailable
from app.review.fallback import journal_by_rules, mapping_by_rules
from app.review.grounding import Grounded, ground_journal, ground_mapping, journal_facts, mapping_facts
from app.review.units import Unit, journal_units, mapping_units


@dataclass(frozen=True)
class UnitResult:
    unit: Unit
    source: str  # "model" or "rules"
    grounded: Grounded
    note: str = ""
    missed: tuple[str, ...] = ()  # exact facts the model did not report: it disagrees with the rules


def coa_view(ctx: Context) -> dict[str, dict[str, str]]:
    return {c: {"name": a.name, "statement": a.statement} for c, a in ctx.inputs.coa.items()}


def review_unit(ctx: Context, cfg: LlmConfig, ledger: Ledger, unit: Unit, mode: Mode = "replay") -> UnitResult:
    coa = coa_view(ctx)
    try:
        if unit.kind == "journal":
            grounded = ground_journal(review_journal(cfg, ledger, unit.packet, mode), unit.packet)
            facts = journal_facts(unit.packet)
        else:
            mapping = review_mapping(cfg, ledger, unit.packet, tuple(sorted(coa)), mode)
            grounded = ground_mapping(mapping, unit.packet, coa)
            facts = {"sign_unusual": mapping_facts(unit.packet, coa)[0]["sign_unusual"]}
        missed = tuple(k for k, v in facts.items() if v and k not in grounded.verified)
        return UnitResult(unit, "model", grounded, missed=missed)
    except LlmUnavailable as why:
        if unit.kind == "journal":
            return UnitResult(unit, "rules", ground_journal(journal_by_rules(unit.packet), unit.packet), str(why))
        return UnitResult(unit, "rules", ground_mapping(mapping_by_rules(unit.packet, coa), unit.packet, coa), str(why))


def review_all(ctx: Context, cfg: LlmConfig, ledger: Ledger, mode: Mode = "replay") -> list[UnitResult]:
    return [review_unit(ctx, cfg, ledger, u, mode) for u in mapping_units(ctx) + journal_units(ctx)]
