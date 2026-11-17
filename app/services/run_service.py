"""Run a consolidation end to end: load the inputs, check them, consolidate, verify, write."""
from dataclasses import dataclass, field
from pathlib import Path

from app.config import load_assumptions, load_policy
from app.core.acquisition import AcquisitionFigures, acquisition_figures, india_period_postings
from app.core.eliminate import ic_balances, ic_income_expense, investments
from app.core.intercompany import IcResult, reconcile
from app.core.post_journals import decide, import_postings, journal_postings
from app.core.revalue import RevalueResult, revalue
from app.core.translate import ConsolidationBlocked, translate
from app.detectors.mapping import classified
from app.detectors.registry import run_all
from app.domain.entries import Entry, Posting
from app.domain.findings import Finding
from app.domain.journals import Disposition
from app.domain.ledger import MappedLine
from app.domain.runs import Context, Inputs
from app.parsers.acquisition_note import load_acquisition
from app.parsers.entities import load_entities, load_intercompany, load_prior_equity, load_subledger
from app.parsers.fx_rates import FxTable, load_rates
from app.parsers.journals import load_journals
from app.parsers.mappings import apply_mapping, load_coa, load_map
from app.parsers.tb_adapters import load_india_monthly, load_tb
from app.utils.paths import CONFIG_DIR


def load_inputs(data_dir: Path) -> Inputs:
    """Read every supplied file. An entity reports in group codes when it has no map file (the US)."""
    entities = load_entities(data_dir / "entities.csv")
    maps = {
        entity: load_map(data_dir / f"map_{entity.lower()}.csv", entity)
        for entity in entities if (data_dir / f"map_{entity.lower()}.csv").exists()
    }
    return Inputs(
        data_dir=data_dir,
        entities=entities,
        trial_balances={e.id: load_tb(data_dir / e.tb_file, e.id, e.currency) for e in entities.values()},
        maps=maps,
        coa=load_coa(data_dir / "group_coa.csv"),
        rates=load_rates(data_dir / "fx_rates.csv"),
        journals=load_journals(data_dir / "adjustments.json"),
        intercompany=load_intercompany(data_dir / "intercompany.csv"),
        subledger=load_subledger(data_dir / "subledger_controls.csv"),
        prior_equity=load_prior_equity(data_dir / "prior_year_group.csv"),
        acquisition=load_acquisition(data_dir / "acquisition_note.md"),
        india_monthly=load_india_monthly(data_dir / "in_pl_monthly.csv"),
    )


def build_context(data_dir: Path, config_dir: Path = CONFIG_DIR) -> Context:
    return Context(
        inputs=load_inputs(data_dir),
        policy=load_policy(config_dir / "policy.toml"),
        assumptions=load_assumptions(config_dir / "assumptions.toml"),
    )


@dataclass
class Consolidation:
    """Everything one run produced, kept so every figure can be traced and every step re-checked."""

    ctx: Context
    findings: list[Finding] = field(default_factory=list)
    mapped: list[MappedLine] = field(default_factory=list)
    dispositions: list[Disposition] = field(default_factory=list)
    local: list[Posting] = field(default_factory=list)
    revalue: RevalueResult | None = None
    ic: IcResult | None = None
    translated: list[Posting] = field(default_factory=list)
    acquisition: AcquisitionFigures | None = None
    eliminations: list[Entry] = field(default_factory=list)
    blocked: str | None = None


def stage(ctx: Context) -> Consolidation:
    """Post, revalue, translate, eliminate, goodwill. A missing input blocks the run from there; it never crashes."""
    fx = FxTable(ctx.inputs.rates)
    result = Consolidation(ctx=ctx, findings=run_all(ctx))
    try:
        result.mapped = apply_mapping(classified(ctx), ctx.assumptions)
        result.dispositions = decide(ctx.inputs.journals, result.findings, ctx.assumptions)
        local = india_period_postings(import_postings(result.mapped), ctx.inputs)
        local += journal_postings(ctx.inputs, ctx.inputs.journals, result.dispositions)
        result.revalue, result.ic = revalue(result.mapped, fx), reconcile(ctx.inputs, fx)
        for entry in result.revalue.entries + result.ic.entries:
            local += list(entry.lines)
        result.local = local
        result.translated = translate(local, ctx.inputs, fx, ctx.policy.period.end)
        result.acquisition = acquisition_figures(ctx.inputs, fx, local, result.translated)
        residual = ctx.policy.intercompany.residual_account
        result.eliminations = [ic_balances(result.translated), ic_income_expense(result.translated, residual)]
        result.eliminations += investments(ctx.inputs, local, result.translated, result.acquisition)
    except ConsolidationBlocked as stop:
        result.blocked = str(stop)
    return result
