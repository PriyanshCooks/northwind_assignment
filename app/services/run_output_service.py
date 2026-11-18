"""What a finished consolidation leaves behind: output files, evidence store rows, and the hash naming a run."""
from pathlib import Path

from app.core.lineage import build_traces, origin_rows
from app.db.connection import connect
from app.db.findings_service import upsert_findings
from app.db.lineage_service import store_origin_rows, store_trace
from app.db.runs_service import create_run
from app.services.run_service import OUTPUT_FILES, Consolidation
from app.utils.hashing import json_hash, sha256_file
from app.utils.paths import CONFIG_DIR
from app.writers.consolidated_tb import write_consolidated_tb
from app.writers.control_figures import write_control_figures
from app.writers.eliminations import write_eliminations
from app.writers.issues import write_issues
from app.writers.manifest import write_manifest
from app.writers.statements import write_statements


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
