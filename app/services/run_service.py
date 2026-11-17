"""Run a consolidation end to end: load the inputs, check them, consolidate, verify, write."""
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from app.config import load_assumptions, load_overrides, load_policy, override_switches
from app.core.acquisition import AcquisitionFigures, acquisition_figures, india_period_postings
from app.core.eliminate import ic_balances, ic_income_expense, investments
from app.core.figures import all_unknown, build_figures
from app.core.intercompany import IcResult, reconcile
from app.core.lineage import build_traces, origin_rows
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
from app.db.connection import connect
from app.db.findings_service import upsert_findings
from app.db.lineage_service import store_origin_rows, store_trace
from app.db.runs_service import create_run
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
from app.services.overrides_service import active_overrides
from app.utils.hashing import json_hash, sha256_file
from app.utils.paths import CONFIG_DIR
from app.verification.invariants import Check, check_invariants
from app.verification.oracle import oracle_checks
from app.writers.consolidated_tb import write_consolidated_tb
from app.writers.control_figures import write_control_figures
from app.writers.eliminations import write_eliminations
from app.writers.issues import write_issues
from app.writers.manifest import write_manifest
from app.writers.statements import write_statements


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
    inputs = load_inputs(data_dir)
    decisions = active_overrides(load_overrides(config_dir / "overrides.toml"), inputs)
    return Context(
        inputs=inputs,
        policy=load_policy(config_dir / "policy.toml"),
        assumptions=load_assumptions(config_dir / "assumptions.toml") | override_switches(decisions),
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
    checks: list[Check] = field(default_factory=list)
    blocked: str | None = None
    log_path: Path | None = None

    @property
    def checks_passed(self) -> bool:
        return all(c.ok for c in self.checks)


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
    tolerance = Decimal(str(run.ctx.assumptions["oracle_tolerance"]))  # assumption A12
    run.checks = check_invariants(
        inputs, run.mapped, run.local, run.revalue.entries + run.ic.entries, run.eliminations, run.balances,
        run.statements, run.reserve, tolerance,
    )
    remap = run.ctx.assumptions.get("map_uk_2310") == "remap_2300"
    run.checks += oracle_checks(inputs.data_dir, run.figures, tolerance, remap)


OUTPUT_FILES = [
    "consolidated_tb.csv", "balance_sheet.json", "profit_and_loss.json", "changes_in_equity.json",
    "eliminations.csv", "issues.json", "control_figures_pb.json", "control_figures_status.json",
]


def write_outputs(run: Consolidation, out_dir: Path, config_dir: Path = CONFIG_DIR) -> None:
    """The required files plus the run manifest. Rounding to 2 decimals happens in the writers, nowhere else."""
    out_dir.mkdir(parents=True, exist_ok=True)
    if run.blocked is None:
        write_consolidated_tb(run, out_dir)
        write_eliminations(run, out_dir)
        write_statements(run, out_dir)
    write_issues(run, out_dir)
    write_control_figures(run, out_dir)
    written = [name for name in OUTPUT_FILES if (out_dir / name).exists()]
    write_manifest(run.ctx.inputs.data_dir, out_dir, written, config_dir)


def record(run: Consolidation, db_path: Path, config_dir: Path = CONFIG_DIR) -> str:
    """Keep the findings, origin rows and traces in the evidence store so `trace` can answer later."""
    inputs_hash = input_hash(run.ctx.inputs.data_dir, config_dir)
    conn = connect(db_path)
    create_run(conn, inputs_hash[:16], inputs_hash, {"blocked": run.blocked, "checks_passed": run.checks_passed})
    upsert_findings(conn, inputs_hash[:16], run.findings)
    if run.blocked is None:
        store_origin_rows(conn, inputs_hash[:16], origin_rows(run))
        for figure, steps in build_traces(run).items():
            store_trace(conn, inputs_hash[:16], figure, steps)
    conn.close()
    return inputs_hash[:16]


RUN_CONFIG_FILES = ("policy.toml", "assumptions.toml", "overrides.toml")


def input_hash(data_dir: Path, config_dir: Path = CONFIG_DIR) -> str:
    """Data and the three config files that change a figure, so an approved override is a new run."""
    parts = {p.name: sha256_file(p) for p in sorted(data_dir.iterdir()) if p.is_file()}
    parts.update({"config/" + n: sha256_file(config_dir / n) for n in RUN_CONFIG_FILES if (config_dir / n).exists()})
    return json_hash(parts)
