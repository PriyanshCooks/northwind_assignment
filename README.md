# Northwind Group consolidation

Consolidates a three-entity, multi-currency group (a US parent, a UK subsidiary and an 80% Indian subsidiary) into GBP
for FY2024 and produces its statements. An AI review layer reads the data and **can only recommend**.
Assignment bundle ID **NWG-D0BC**.

> **Status: the engine, the LangGraph orchestration, the AI review and reasoning layers and a local review page are built.**
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
│   ├── main.py  routes.py  api_models.py  cli.py  cli_review.py  config.py
│   ├── agents/              every AI reader, none imports core
│   │   ├── journal_reviewer/  mapping_reviewer/   per-unit reviewers: llm_model.py  prompts.py  schema.py  tools.py
│   │   ├── review/          review units, evidence packets, grounding of those two reviewers' answers
│   │   └── reasoning/       read-only reasoning checkpoints, claim grounding, injection guard
│   ├── orchestrator/        the LangGraph workflow
│   ├── llm/                 the only code that talks to a model provider
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
                              # seven stages: upload, scan, review inputs, choose outputs, generate, review outputs, done
python run.py whatif --patch "fx_rates.csv:6.rate=1.30"   # re-run on a patched copy: figures, accounts and findings that move
```

Tests and checks: `python -m pytest && python -m ruff check . && python -m mypy app`

## Switching the AI model

Set `model` in `config/llm.toml`, or the `NORTHWIND_MODEL` environment variable. Strings: `ollama:<model>`,
`openai:<model>`, `google:<model>`, `anthropic:<model>`. Keys come from environment variables (see `.env.example`). No model output is a
number: the 12 control figures are computed without a model, and `tests/unit/llm/test_switch.py` and the red-team tests check that.

## What is built

| Area | State |
|---|---|
| Supplied data with integrity checksums | Present (`Northwind_TakeHome_v2/data/`, `config/bundle_manifest.sha256`) |
| Settings: policy, assumptions, overrides, model | Present (`config/`); policy values are bound to `group_policies.md` by hash |
| Parsers, schema contracts and the three trial-balance adapters | Built, tested |
| Detectors D01 to D15 | Built, tested: each known defect in the data gives exactly one finding; D15 (rate plausibility, amber, tolerances ASSUMED) raises nothing on the supplied data |
| Input validation: impossible rates, percentages, dates and amounts stop the run with file, line and column (exit 2, API 422) | Built, tested with a table of perturbations |
| Journal dispositions, posting, revaluation, intercompany, translation, eliminations, goodwill, NCI | Built, tested |
| Translation reserve by two routes, statements, the 12 control figures | Built, tested |
| Invariants and an oracle: a second implementation of the same method that recomputes the figures from the raw files | Built, tested; 20 checks run on every consolidation |
| Lineage, `trace`, run manifest, JSON-lines run log, `run.py check` | Built, tested |
| Golden test against the hand calculation | Passing; the hand calculation is AI-written and not yet human-reviewed |
| Continuous integration workflow | Present; not yet seen green on Linux |
| Orchestration with pause and resume (LangGraph and a plain runner with identical outputs), `whatif`, `impact`, review queue, API | Built, tested |
| AI reviewers, reasoning layer, model ledger (replay), model switch | Built, tested on recorded answers. The AI only advises: its recall on labelled faults is low, so the rules are the detector. The run needs no model |
| Sign-off: files marked reviewed against their hash, Final or Draft written to `signoff.json` in the export | Built, tested. D06 and D07 can be acknowledged but have no engine override |
| Review page: `app/main.py`, `routes*.py`, run registry under `.northwind/runs/`, `frontend/` (plain files, no build) | Built, tested with `TestClient`; walked once in a browser |
| `docs/CODE_GUIDE.md` | Present and current |
| `docs/ARCHITECTURE.md`, `DECISIONS.md`, `VALIDATION.md`, `REFLECTION.md` | Placeholders until the final documents are written |
