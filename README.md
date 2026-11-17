# Northwind Group consolidation

Consolidates a three-entity, multi-currency group (a US parent, a UK subsidiary and an 80% Indian subsidiary) into GBP
for FY2024 and produces its statements. An AI review layer reads the data and **can only recommend**.
Assignment bundle ID **NWG-D0BC**.

> **Status: structure, tooling and guard tests only.** The application code is built wave by wave; every module is a
> docstring-only shell until its wave. The table at the end says exactly what exists.

## Principles

1. Every number on a statement is computed by deterministic code on `Decimal`. No model output is a number.
2. The AI layer recommends; a rule or a human decides. Free text in the data is quarantined and never obeyed.
3. A figure that cannot be determined is `null` with a reason. Nothing is estimated.
4. Every figure traces back to `file:line`. The same inputs give identical bytes.

## Layout

```
.
├── Northwind_TakeHome_v2/   the supplied assignment: brief PDF, its README, data/ (never edited)
├── app/                     the application
│   ├── main.py  routes.py  api_models.py  cli.py  config.py
│   ├── agents/              one folder per AI reviewer: llm_model.py  prompts.py  schema.py  tools.py
│   ├── orchestrator/        the LangGraph workflow
│   ├── llm/                 the only code that talks to a model provider
│   ├── review/              review units, evidence packets, grounding checks
│   ├── core/                the deterministic consolidation
│   ├── parsers/  detectors/  verification/  writers/  domain/
│   └── db/  services/  utils/
├── frontend/                review UI (plain static files)
├── tests/                   unit, golden, perturbation, property, red-team, eval and architecture tests
├── config/                  human-edited settings: policy, assumptions, overrides, llm; data checksums
├── ledger/                  recorded AI calls, one file per model
├── output/                  generated results
├── docs/                    the architecture document and the code guide
├── transcripts/             full AI session records
├── run.py                   one entry point: consolidate | serve | check
├── README.md  DECISIONS.md  VALIDATION.md  REFLECTION.md
└── pyproject.toml  requirements*.txt  .env.example  .gitignore  .github/
```

**The AI is kept away from the numbers by structure.** The folders that produce or touch a number (`core`, `parsers`,
`detectors`, `verification`, `writers`, `domain`) never import AI or web code, agents never import `core`, and only
`app/llm/` imports a model library. `tests/test_architecture.py` enforces it.

## Setup

Requires Python 3.11 or newer.

```bash
python -m venv .venv
# Windows:  .venv\Scripts\activate        macOS/Linux:  source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
python -m pytest
```

## Run

Until its wave is built, each command prints `not built yet (Wave N)` and exits with code 2.

```bash
python run.py consolidate     # the one command: reads Northwind_TakeHome_v2/data/, writes output/
python run.py serve           # API and review UI on http://127.0.0.1:8000
python run.py check           # environment, data integrity, config
```

Tests and checks: `python -m pytest && python -m ruff check . && python -m mypy app`

## Switching the AI model

Set `model` in `config/llm.toml`, or the `NORTHWIND_MODEL` environment variable. Strings: `ollama:<model>`,
`openai:<model>`, `google:<model>`, `anthropic:<model>`. Keys come from environment variables (see `.env.example`). The
12 control figures are meant to be identical whichever model is used; the test for that arrives with wave 3.

## What is built

| Area | State |
|---|---|
| Supplied data with integrity checksums | Present (`Northwind_TakeHome_v2/data/`, `config/bundle_manifest.sha256`) |
| Settings: policy, assumptions, overrides, model | Present (`config/`) |
| Continuous integration workflow | Present (`.github/workflows/ci.yml`) |
| Folder structure of `app/` and `tests/`, with docstring-only shells | Present; no logic yet |
| `run.py` with `consolidate`, `serve`, `check` | Present as stubs that print `not built yet (Wave N)` |
| `pyproject.toml` and pinned `requirements*.txt` | Present (checked against PyPI) |
| Structure, import-boundary and data-checksum tests | Present and passing (`tests/test_structure.py`, `test_architecture.py`, `test_bundle.py`) |
| Parsers, detectors, consolidation, statements, outputs (wave 1) | Not built |
| Orchestration, API (wave 2); AI layer and ledger (wave 3) | Not built |
| Golden figures test, perturbation, property and red-team tests | Not built |
| `frontend/` | `README.md` only |
| `docs/CODE_GUIDE.md` | Present; describes the structure, tooling and tests only |
