"""The repository has exactly the files the structure document lists, and each agent has its four files."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

APP_FILES = {
    "app": ["main.py", "routes.py", "routes_results.py", "routes_inputs.py", "routes_signoff.py", "api_models.py",
            "cli.py", "cli_review.py", "config.py"],
    "app/agents": [],
    "app/agents/reasoning": [
        "evidence.py", "tools.py", "schema.py", "grounding.py", "contradiction.py", "text_checks.py",
        "meanings.py", "reader.py", "budget.py", "calc_review.py", "investigator.py", "explain.py",
    ],
    "app/orchestrator": ["state.py", "nodes.py", "edges.py", "graph.py", "runner_plain.py"],
    "app/llm": ["client.py", "factory.py", "ledger.py", "instrumentation.py", "replay.py", "cost.py", "tooluse.py"],
    "app/agents/review": ["units.py", "packets.py", "grounding.py", "fallback.py", "verdict.py"],
    "app/core": [
        "post_journals.py", "revalue.py", "translate.py", "intercompany.py", "eliminate.py",
        "acquisition.py", "reserve.py", "statements.py", "figures.py", "lineage.py", "calculations.py",
    ],
    "app/parsers": [
        "contracts.py", "tb_adapters.py", "journals.py", "mappings.py", "fx_rates.py",
        "entities.py", "acquisition_note.py", "policy_text.py", "ranges.py",
    ],
    "app/detectors": [
        "registry.py", "balance.py", "mapping.py", "journals.py", "rates.py",
        "reconciliation.py", "text_scan.py", "expectations.py", "duplicates.py",
    ],
    "app/verification": ["invariants.py", "oracle.py", "recalc.py"],
    "app/writers": [
        "consolidated_tb.py", "statements.py", "eliminations.py", "issues.py", "control_figures.py", "manifest.py",
    ],
    "app/domain": [
        "refs.py", "quarantine.py", "ledger.py", "journals.py", "findings.py",
        "entries.py", "figures.py", "policy.py", "runs.py", "calculations.py",
    ],
    "app/db": [
        "connection.py", "schema.sql", "runs_service.py",
        "findings_service.py", "lineage_service.py", "checkpoint.py",
    ],
    "app/services": [
        "run_service.py", "trace_service.py", "whatif_service.py", "overrides_service.py", "env_service.py",
        "review_service.py", "registry_service.py", "upload_service.py", "pipeline_service.py", "results_service.py",
        "ai_service.py", "cards_service.py", "output_service.py", "reasoning_service.py", "rows_service.py",
        "rule_text.py", "inputs_service.py", "scan_service.py",
        "decisions_service.py", "review_actions_service.py", "generate_service.py", "signoff_service.py",
        "calculation_service.py", "row_explain_service.py", "run_output_service.py",
    ],
    "app/utils": ["env.py", "hashing.py", "logging.py", "money.py", "paths.py"],
}
AGENT_FILES = ["llm_model.py", "prompts.py", "schema.py", "tools.py"]
FULL_AGENTS = ["mapping_reviewer", "journal_reviewer"]
TEST_FOLDERS = ["unit", "perturbation", "property", "redteam", "evals", "api"]
UNIT_FOLDERS = [folder.removeprefix("app/") for folder in APP_FILES if folder != "app"]
TOP_LEVEL = [
    "run.py", "README.md", "DECISIONS.md", "VALIDATION.md", "REFLECTION.md", "pyproject.toml",
    "requirements.txt", "requirements-dev.txt", "requirements-llm.txt", "requirements-constraints.txt",
    ".env.example", ".gitignore",
    ".gitattributes", ".github/workflows/ci.yml", "docs/ARCHITECTURE.md", "ledger/README.md",
    "transcripts/README.md", "config/policy.toml", "config/assumptions.toml", "config/overrides.toml",
    "config/llm.toml", "config/pricing.toml", "config/bundle_manifest.sha256", "frontend/README.md",
]


def files_under(folder: str) -> set[str]:
    base = ROOT / folder
    return {p.relative_to(ROOT).as_posix() for p in base.rglob("*") if p.is_file() and "__pycache__" not in p.parts}


def expected_app_files() -> set[str]:
    expected = {f"{folder}/__init__.py" for folder in APP_FILES}
    expected |= {f"{folder}/{name}" for folder, names in APP_FILES.items() for name in names}
    for agent in FULL_AGENTS:
        expected |= {f"app/agents/{agent}/__init__.py"} | {f"app/agents/{agent}/{name}" for name in AGENT_FILES}
    return expected


def test_app_has_exactly_the_listed_files() -> None:
    actual, expected = files_under("app"), expected_app_files()
    assert sorted(expected - actual) == [], "listed but missing"
    assert sorted(actual - expected) == [], "present but not listed"


def test_each_full_agent_has_its_four_files_and_nothing_else() -> None:
    for agent in FULL_AGENTS:
        names = {p.name for p in (ROOT / "app/agents" / agent).iterdir() if p.is_file()}
        assert names == {"__init__.py", *AGENT_FILES}, agent


def test_every_app_and_test_folder_is_a_package() -> None:
    every = [p for base in ("app", "tests") for p in (ROOT / base).rglob("*") if p.is_dir()]
    folders = [p for p in every if "__pycache__" not in p.parts and p.name != "golden"]
    missing = [p.relative_to(ROOT).as_posix() for p in folders if not (p / "__init__.py").is_file()]
    assert missing == []


def test_test_folders_mirror_the_structure() -> None:
    for name in TEST_FOLDERS:
        assert (ROOT / "tests" / name / "__init__.py").is_file(), name
    for name in UNIT_FOLDERS:
        assert (ROOT / "tests/unit" / name / "__init__.py").is_file(), name
    assert (ROOT / "tests/conftest.py").is_file()
    assert (ROOT / "tests/golden").is_dir()


def test_frontend_is_plain_static_files() -> None:
    names = ("README.md", "index.html", "style.css", "app.js", "format.js", "issues.js", "ai.js", "viewer.js",
             "steps.js", "workbench.js")
    assert files_under("frontend") == {f"frontend/{n}" for n in names}


def test_top_level_files_exist() -> None:
    missing = [name for name in TOP_LEVEL if not (ROOT / name).is_file()]
    assert missing == []
