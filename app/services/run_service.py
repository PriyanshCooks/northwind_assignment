"""Run a consolidation end to end: load the inputs, check them, consolidate, verify, write."""
from pathlib import Path

from app.config import load_assumptions, load_policy
from app.domain.runs import Context, Inputs
from app.parsers.acquisition_note import load_acquisition
from app.parsers.entities import load_entities, load_intercompany, load_prior_equity, load_subledger
from app.parsers.fx_rates import load_rates
from app.parsers.journals import load_journals
from app.parsers.mappings import load_coa, load_map
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
