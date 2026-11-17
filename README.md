# Northwind Group consolidation

Consolidates a three-entity, multi-currency group (a US parent, a UK subsidiary and an 80% Indian subsidiary) into GBP
for FY2024 and produces its statements. An AI review layer reads the data and **can only recommend**.
Assignment bundle ID **NWG-D0BC**.

> **Status: the engine, orchestration, the AI review layer and a local review page are built.**
> `python run.py consolidate` writes the required outputs. The table at the end says exactly what exists.

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

```bash
python run.py consolidate     # the one command: reads Northwind_TakeHome_v2/data/, writes output/
python run.py trace goodwill_closing   # walk a figure (or an account such as 1100) down to file:line
python run.py check           # Python version, data integrity, policy binding
python run.py serve           # review page at http://127.0.0.1:8000/ (this machine only, no live model call)
                              # seven steps: upload, review (issue cards and the recorded AI review), outputs, build,
                              # results, output file viewer, export
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
| Settings: policy, assumptions, overrides, model | Present (`config/`); policy values are bound to `group_policies.md` by hash |
| Parsers, schema contracts and the three trial-balance adapters | Built, tested |
| Detectors D01 to D14 | Built, tested: each known defect in the data gives exactly one finding |
| Journal dispositions, posting, revaluation, intercompany, translation, eliminations, goodwill, NCI | Built, tested |
| Translation reserve by two routes, statements, the 12 control figures | Built, tested |
| Invariants and an oracle: a second implementation of the same method that recomputes the figures from the raw files | Built, tested; 20 checks run on every consolidation |
| Lineage, `trace`, run manifest, JSON-lines run log, `run.py check` | Built, tested |
| Golden test against the hand calculation | Passing; the hand calculation is AI-written and not yet human-reviewed |
| Continuous integration workflow | Present; not yet seen green on Linux |
| Orchestration with pause and resume, `whatif`, review queue, API | Not built (wave 2) |
| AI reviewers, model ledger, model switch | Not built (wave 3); the run needs no model |
| Review page: `app/main.py`, `routes*.py`, run registry under `.northwind/runs/`, `frontend/` (plain files, no build) | Built, tested with `TestClient`; walked once in a browser |
| `docs/CODE_GUIDE.md` | Present; covers wave 0 and wave 1 |
