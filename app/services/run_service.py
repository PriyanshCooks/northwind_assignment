"""Run a consolidation end to end: load the inputs, check them, consolidate, verify, write."""
from dataclasses import dataclass, field
from pathlib import Path

from app.config import load_assumptions, load_policy
from app.core.acquisition import AcquisitionFigures, acquisition_figures, india_period_postings
from app.core.eliminate import ic_balances, ic_income_expense, investments
from app.core.figures import all_unknown, build_figures
from app.core.intercompany import IcResult, reconcile
from app.core.post_journals import decide, import_postings, journal_postings
from app.core.reserve import ReserveResult, reserve
from app.core.revalue import RevalueResult, revalue
from app.core.statements import (
    Balances,
    EquityView,
    balance_sheet,
    balances_by_account,
    changes_in_equity,
    profit_and_loss,
)
from app.core.translate import ConsolidationBlocked, translate
from app.detectors.mapping import classified
from app.detectors.registry import run_all
from app.domain.entries import Entry, Posting
from app.domain.figures import Figure
from app.domain.findings import Finding
from app.domain.journals import Disposition
from app.domain.ledger import MappedLine
from app.domain.runs import Context, Inputs
from app.parsers.acquisition_note import load_acquisition
from app.parsers.entities import load_entities, load_intercompany, load_prior_equity, load_subledger
from app.parsers.fx_rates import FxTable, load_rates
from app.parsers.journals import load_journals
from app.parsers.mappings import apply_mapping, load_coa, load_map
from app.parsers.policy_text import PolicyBlocked, check_binding
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
    balances: Balances = field(default_factory=dict)
    reserve: ReserveResult | None = None
    statements: dict[str, dict[str, object]] = field(default_factory=dict)
    figures: dict[str, Figure] = field(default_factory=dict)
    blocked: str | None = None


def stage(ctx: Context) -> Consolidation:
    """Post, revalue, translate, eliminate, goodwill. A missing input blocks the run from there; it never crashes."""
    fx = FxTable(ctx.inputs.rates)
    result = Consolidation(ctx=ctx, findings=run_all(ctx))
    try:
        check_binding(ctx.policy, ctx.inputs.data_dir)
        _stop_on_blockers(result.findings)
        result.mapped = apply_mapping(classified(ctx), ctx.assumptions)
        result.dispositions = decide(ctx.inputs.journals, result.findings, ctx.assumptions)
        local = india_period_postings(import_postings(result.mapped), ctx.inputs)
        local += journal_postings(ctx.inputs, ctx.inputs.journals, result.dispositions)
        difference_account = ctx.policy.foreign_currency_items.difference_account
        result.revalue = revalue(result.mapped, fx, difference_account)
        result.ic = reconcile(ctx.inputs, fx)
        for entry in result.revalue.entries + result.ic.entries:
            local += list(entry.lines)
        result.local = local
        result.translated = translate(local, ctx.inputs, fx, ctx.policy.period.end)
        result.acquisition = acquisition_figures(ctx.inputs, fx, local, result.translated)
        residual = ctx.policy.intercompany.residual_account
        result.eliminations = [ic_balances(result.translated), ic_income_expense(result.translated, residual)]
        result.eliminations += investments(ctx.inputs, local, result.translated, result.acquisition)
        _finish(result, fx)
    except (ConsolidationBlocked, PolicyBlocked) as stop:
        result.blocked = str(stop)
        result.figures = all_unknown(result.blocked)
    return result


def _stop_on_blockers(findings: list[Finding]) -> None:
    """A trial balance that does not balance, or files that do not tie, block the run: nothing is guessed."""
    blocking = [f for f in findings if f.severity == "BLOCK" and f.code in {"D01", "D10"}]
    if blocking:
        raise ConsolidationBlocked("; ".join(f"{f.code} {f.claim}" for f in blocking))


def _finish(run: Consolidation, fx: FxTable) -> None:
    """Balances, reserve, statements and the 12 figures, once every posting and elimination exists."""
    inputs, acq = run.ctx.inputs, run.acquisition
    assert acq is not None and run.ic is not None and run.revalue is not None
    run.balances = balances_by_account(run.translated, run.eliminations, inputs.coa)
    run.reserve = reserve(inputs, fx, run.local, run.translated, run.balances, acq)
    equity = EquityView(
        share_capital=inputs.prior_equity["3100"].amount_gbp, retained_opening=inputs.prior_equity["3200"].amount_gbp,
        reserve_opening=run.reserve.opening, nci_opening=inputs.prior_equity["3400"].amount_gbp,
        owners_profit=run.reserve.owners_profit, nci_acquired=acq.nci_at_acquisition, nci_profit=acq.nci_profit,
        nci_translation=acq.nci_translation, reserve_movement=run.reserve.movement_balance,
    )
    period = (run.ctx.policy.period.start, run.ctx.policy.period.end)
    run.statements = {
        "balance_sheet": balance_sheet(run.balances, inputs.coa, equity, period[1]),
        "profit_and_loss": profit_and_loss(run.balances, inputs.coa, period, (equity.owners_profit, acq.nci_profit)),
        "changes_in_equity": changes_in_equity(equity, period),
    }
    run.figures = build_figures(inputs, fx, run.balances, run.reserve, acq, run.ic, run.dispositions, run.revalue)
