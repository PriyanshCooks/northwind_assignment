# Code guide

A plain-English guide to the repository. It describes what exists now; each wave adds to it.
Current state: **Wave 0 done** (structure, tooling, guard tests). No consolidation logic yet.

## Run and test

```bash
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest
python -m ruff check .
python -m mypy app
python run.py consolidate         # prints "not built yet (Wave 1)" and exits 2
```

## What each top-level folder is for

| Folder | Role |
|---|---|
| `Northwind_TakeHome_v2/` | The supplied brief and data. Never edited. |
| `app/` | The application. Every file is a docstring-only shell until its wave. |
| `config/` | Hand-edited TOML settings, and `bundle_manifest.sha256`, the SHA-256 of each supplied data file. |
| `tests/` | `test_structure`, `test_architecture` and `test_bundle` today; unit, golden, perturbation, property, red-team and eval folders later. |
| `ledger/`, `output/`, `transcripts/` | Recorded AI calls, generated results and AI session records. Empty for now. |

## How `app/` is divided

The split exists to keep AI output away from numbers.

- `core`, `parsers`, `detectors`, `verification`, `writers`, `domain` touch numbers. They import no AI, web or
  model code.
- `agents` hold AI reviewers. They never import `core`, so a reviewer can read evidence but cannot calculate.
- `llm` is the only place that imports a model library.
- `db` is the only place that uses `sqlite3`.

`tests/test_architecture.py` reads every source file with Python's `ast` module and fails if one of these rules is
broken. It also tests its own checker on small snippets, so it cannot pass by checking nothing.

## What the three tests prove

- `test_structure.py`: `app/` contains exactly the files in the structure plan (no missing, no extra), every folder is
  a package, each full agent folder has its four files, the stretch agents have only `__init__.py`.
- `test_architecture.py`: the import rules above.
- `test_bundle.py`: the 15 supplied data files hash to the values in `config/bundle_manifest.sha256`. In a fresh clone
  this checks the committed bytes, because `.gitattributes` stops git from changing line endings in the data folder.

## Choices worth explaining

- **Pinned requirements.** Exact versions, so a fresh clone installs what was tested. Pins were checked against PyPI
  on 2026-11-17. `requirements.txt` names the packages the code uses; `requirements-constraints.txt` is the full
  `pip freeze` of the tested environment and is pulled in with `-c`, so transitive packages are fixed too. A clean
  venv installed from these files freezes to exactly that list. The packages for `requirements-llm.txt` are not in
  the constraints file, and `google-genai` is left unpinned until Gemini is first used.
- **TOML for config.** YAML reads `0031` as the number 25; TOML refuses it.
- **No line-ending conversion for the data.** The first commit stored 12 CSV files with changed line endings; the
  second commit ("store data files byte for byte") corrected it.

## Wave 1 module notes

### utils (task 1.0)
- `money.py`: `to_decimal` builds a Decimal from a string or int and refuses a float. `round2` rounds half up and is called only when a figure is written (policy 7, assumption A13). The module sets 50 digits of precision, so translation is exact enough to round once at the end.
- `hashing.py`: SHA-256 helpers and `dumps`, the one JSON writer used for outputs and hashes. It writes a Decimal as a bare number without passing through a float.
- `paths.py`: repository paths. The data folder is a command-line option; the path here is only its default.

### domain (task 1.1)
All models are frozen Pydantic classes in `app/domain/`. The plan called this `types.py`; the structure document is the master, so it is a folder.
- `refs.py`: `SourceRef` (file, line, hash of the raw row) is the unit of traceability. `Money` is a Decimal that refuses a float and is written as a string in JSON.
- `quarantine.py`: `Quarantined` wraps free text. It prints only its length; scanners read `.text`, everything else shows `quoted()`.
- `ledger.py`, `journals.py`: trial-balance lines (debit-positive), mapping rows, the chart of accounts, monthly rows, journals and their dispositions (POST, REJECT, HOLD).
- `findings.py`: one problem with `file:line`, the amount affected and what the system did. Two findings with the same key merge.
- `entries.py`: a `Posting` is one piece of a balance with its origin (IMPORT, JOURNAL, REVALUE, TRANSLATION, ELIMINATION, ACQUISITION) and source rows. An `Entry` must balance.
- `figures.py`: `Determined`, `Provisional` and `Unknown` form a union. An unknown figure carries a reason and has no value field.
- `policy.py`, `runs.py`: policy values, the assumptions registry, the parsed inputs and the run manifest.

### evidence store (task 1.2)
`app/db/connection.py` opens SQLite and applies `schema.sql`; every JSON column has a `json_valid` check, so a malformed document cannot be stored. The service files each own one table family: runs, findings (upsert by key), facts (a decision is stale when its evidence hash changes), recorded AI calls, and origin rows with traces. The database is disposable and rebuilt on every run.

### parsers (task 1.3)
Each input file has a contract in `app/parsers/contracts.py` (columns, decimal and date columns, allowed values). A file that breaks it raises `ContractError` with the file, line and reason. Only outer whitespace is trimmed, so `0031` stays text. `tb_adapters.py` reads the three layouts (debit/credit columns, one signed balance, amount plus Dr/Cr) into one `LedgerLine`, chosen from the header; an unknown header blocks that entity. `fx_rates.py` parses the direction of each rate from the convention column and answers in GBP terms: the product rule for GBP/INR is in `FxTable.units_per_gbp`, and a rate the file does not give returns None. `journals.py` keeps the line each journal and memo starts on, so a finding can point at `adjustments.json:112`.

### detectors (task 1.4)
Each detector is a function from a `Context` (inputs, policy, assumptions) to findings. `registry.run_all` runs all fourteen and merges findings with the same key. D01 and D03 check balance; D02 checks mappings (including the exact-name rule that catches UK 2310 Deferred income mapped to Revenue); D04 to D07 check journals (period, duplicates, accounts through the entity map, reversals past zero); D08 needs rates; D09 to D11 tie files together; D12 scans free text; D13 notes the tax step and identical months; D14 flags exact duplicate rows. Findings never change a number: the consolidation reads them only to decide a journal disposition (task 1.6).

### mapping (task 1.5)
`classify_all` gives every trial-balance line a verdict and `apply_mapping` applies the assumption switches. A suspect mapping is only changed when the switch for that account is set in `config/assumptions.toml` (`map_uk_2310 = "remap_2300"`). Unmapped and ambiguous lines get no group account and are carried in a suspense line, so mapping never changes a total.

### journals (task 1.6)
`core/post_journals.py` turns trial-balance lines into IMPORT postings and decides each journal: REJECT when invalid for FY2024 (unbalanced, outside the period, duplicate), HOLD when a human must look (account not in the entity chart, reversal past zero), otherwise POST. The decision reads only detector findings and the assumption switches, never the free text of a memo. Posted journals go through the entity map, so UK `7100` (rent) becomes group `6200`, not group `7100` (finance costs).
