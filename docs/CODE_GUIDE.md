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
`classify_all` gives every trial-balance line a verdict and `apply_mapping` applies the assumption switches. A suspect mapping is only changed when a human decision in `config/overrides.toml` approves it (UK 2310 to 2300, status `open` until someone signs it off; `load_overrides` turns it into the `map_uk_2310` switch). Reversing it, by deleting the row, adds 180,000 GBP to group revenue and profit. Unmapped and ambiguous lines get no group account and are carried in a suspense line, so mapping never changes a total.

### journals (task 1.6)
`core/post_journals.py` turns trial-balance lines into IMPORT postings and decides each journal: REJECT when invalid for FY2024 (unbalanced, outside the period, duplicate), HOLD when a human must look (account not in the entity chart, reversal past zero), otherwise POST. The decision reads only detector findings and the assumption switches, never the free text of a memo. Posted journals go through the entity map, so UK `7100` (rent) becomes group `6200`, not group `7100` (finance costs).

### revaluation and intercompany (task 1.7)
`core/revalue.py` restates a foreign-currency monetary line at the closing rate (policy 3) and books the difference to 7300; a line whose rate is missing is reported, never guessed. `core/intercompany.py` pairs the two sides by document reference, records an invoice the receiver has not booked at the closing rate (policy 5) and splits the difference into in-transit plus revaluation. Both produce balanced `Entry` objects whose postings cite the source rows and the rate row used.

### translate (task 1.8)
`core/translate.py` applies policy 2: closing rate for assets and liabilities, the average rate for the period the entity was owned for income and expenses. Which average applies is derived from the entity acquisition date and the rate windows in `fx_rates.csv`. Equity accounts are not translated here (group equity comes from `prior_year_group.csv` plus the reserve, see task 1.10). Every translated posting keeps its source rows and names the rate rows it used.

### acquisition and elimination (task 1.9)
`core/acquisition.py` splits India nine-month trial balance at the completion month: income and expense come from the monthly file for the months owned, and profit before completion is carried to reserves. It also computes goodwill (consideration less 80% of net assets at completion, held in INR and retranslated at closing) and non-controlling interest (20% of net assets, proportionate method). `core/eliminate.py` builds the balanced elimination entries: intercompany balances, intercompany income and expense (the rate difference goes to 7300) and the two investments. Equity legs of the investment entries are for the auditor; consolidated equity is built from the prior-year file in the reserve step.

### reserve, statements and figures (task 1.10)
`core/reserve.py` computes the translation reserve two ways. The balance route treats equity as fixed by net assets: the reserve is what remains after share capital, retained earnings (opening plus the owners share of profit) and non-controlling interest. The components route adds up named exchange differences: US opening net assets and profit, India net assets, profit and goodwill, less the retranslation of the two investments the group eliminates. The two must agree within a cent. `core/statements.py` builds the balance sheet, profit and loss and changes in equity. `core/figures.py` produces the twelve control figures; a figure that depends on the missing SGD rate is Provisional with that open item, and the SGD balance itself is Unknown with its reason.

### policy binding (task 1.11)
`config/policy.toml` holds the policy values the engine reads (difference accounts, the intercompany residual account, the reporting period). It records the SHA-256 of `group_policies.md`. `check_binding` compares that hash with the file on every run; if the policy text changed and nobody re-approved `policy.toml`, the run is blocked and every figure is `null` with the reason. Reading clauses automatically is a Wave 3 task.

### verification (task 1.12)
`app/verification/invariants.py` holds checks that must hold for any input; a failing check marks the run failed instead of being adjusted away. `app/verification/oracle.py` is a second implementation of the same method: it recomputes the control figures from the raw files with separate code (no imports from `core` or `parsers`), working per entity in local currency. The pipeline and the oracle must agree within a cent. It is not independent: it follows the same policy and shares the assumptions (A1, A3, A6, A9, the 2310 remap switch), so agreement shows the code is wired the same way, not that the accounting is right. It catches slips and wiring errors, not a misreading of the policy; that is what the hand calculation and the review are for.

### lineage, outputs and commands (task 1.13)
`core/lineage.py` lists the postings every consolidated balance is made of and builds a trace per figure. `app/writers/` writes the required files: values are rounded to 2 decimals only there (`round_tree`). `consolidated_tb.csv` and `eliminations.csv` cite `file:line` for every row. `run_manifest.json` records input, policy, assumption and code hashes plus a hash of every other output, so two runs on the same inputs can be compared byte for byte. `run.py consolidate` runs everything and stores findings, origin rows and traces in `.northwind/run.db`; `run.py trace goodwill_closing` (or an account such as `1100`) walks a result down to the source rows; `run.py check` verifies the data bundle and the policy binding.

### run log (task 1.14)
`app/utils/logging.py` writes one JSON line per event to `.northwind/logs/`. Each line has `run_id`, `stage` and `event`; finding events carry the finding key and gate events the check name and result. Timestamps live only in this log, so the required outputs are byte-identical between runs while the logs differ.

## Wave 2 module notes

### overrides and the review queue (task 2.2)
`config/overrides.toml` holds human decisions. Each one stores an `evidence_hash`: the hash of the mapping row and the trial balance row the reviewer looked at. `services/overrides_service.py` classifies every override on each run: `applied` (approved, evidence unchanged), `open` (not yet signed off, still applied and reversible), `stale` (the evidence changed, so it stops applying) or `rejected`. `build_context` feeds only applied and open ones into the run. `review_queue` lists open and stale overrides first, then every flagged or blocked finding; notes are left out. To say in the live session: a decision is only valid for the evidence it was made on, so an input change puts the item back in front of a person instead of silently carrying an old approval forward.

### the LangGraph workflow (task 2.1)
`app/orchestrator/` runs five stages: intake, analyse, resolve, consolidate, export (`nodes.py`). `graph.py` wires them; after analyse, `edges.after_analyse` sends the run to resolve only if an override is open or stale. Resolve calls `interrupt()`, so the run stops and its place is saved in `.northwind/checkpoints.db` under the thread `run-<input hash>`. `python run.py resume --thread T --approver NAME --approve mapping:UK:2310` answers it from another process: the answer is written into `config/overrides.toml` with the evidence hash and the run continues. The state holds only paths, the run id, status and open item keys; each node rebuilds what it needs from the files (about 20 ms), which keeps the checkpoint small and the answer to "where did this number come from" in one place. LangGraph reruns the interrupted node from its top on resume, so nothing with a side effect happens before `interrupt()`.

### the plain runner (task 2.3)
`runner_plain.run_plain` calls the same node functions in order, with no LangGraph. `python run.py consolidate --engine plain` uses it. With an override waiting and no answer it stops at the human gate (status `awaiting_review`), as the graph does. The tests run both runners on the same inputs and compare the SHA-256 of every output file, including `run_manifest.json`; they also compare a graph that was paused and resumed against a plain run that was given the same answer. To say live: if LangGraph will not install on a reviewer's machine, the plain engine gives the same bytes.

### whatif, impact and diff-inputs (task 2.4)
`services/whatif_service.py` copies the input folder to a temporary directory, applies the change and runs the whole consolidation on the copy; the supplied files are never written (a test hashes them before and after). `python run.py whatif --patch fx_rates.csv:6.rate=1.30` sets one cell (line numbers count the header as 1, line endings are kept); `--append "fx_rates.csv=GBP,SGD,closing,1.7300,2024-12-31,SGD per 1 GBP"` adds a row; `--set je017=post` flips an assumption for that run. The output is the control figures that changed and the group accounts that moved. `impact fx_rates.csv:6` nudges the row's rightmost number by 1% and prints what moved: it is measured, not read from a diagram. `diff-inputs OLD_FOLDER` lists the files and line numbers that differ from an older copy. To say live: change an input, predict which figures move, run whatif, compare.

### perturbation and property tests (task 2.5)
`tests/perturbation/` changes one input at a time on a copy and checks two things: the invariants and the oracle still hold, and the figure moves by the amount worked out by hand (US revenue +1,000 USD gives +782.47 GBP at the 1.2780 average). Cases: US revenue, four rates, a new SGD closing rate, an intercompany invoice, an unbalanced trial balance (every figure null with a reason), posting JE-017, a missing rate, and a closing rate that leaves a repeating decimal. `tests/property/` uses Hypothesis to change five rates (60% to 160%) and a balanced US posting at random and requires every non-oracle check to pass. Two things these tests taught us, kept as tests: the full-year INR average feeds no figure (India is translated at the H2 average, policy 3), and the oracle cannot follow an SGD closing rate (it keeps the bank at booked value), so it disagrees by exactly 111.39 when one is added. The property test found a real defect: the elimination-balance invariant compared a 50-digit Decimal to exactly zero, which fails by about 1e-48 at some rates; it now uses the 0.000001 tolerance the other invariants use.

### status sidecar and the strict control figures check (task 2.6)
`control_figures_pb.json` holds the 12 keys, each a number or `null` (`journals` is posted, rejected and held counts). The reason for a `null` and the open items behind a provisional figure live in `control_figures_status.json`, so the required file keeps the shape the brief asks for. `tests/unit/writers/test_control_figures_schema.py` validates the file with a strict Pydantic model (no extra keys, no numbers as strings, no booleans) on the supplied data and on a blocked run, and checks that every `null` has a reason and every provisional figure names its open items.

## Wave 3 module notes

### the model adapter and ledger (task 3.1)
`app/llm/` is the only place that imports `pydantic_ai`. `client.run_structured` makes one typed call. In `replay` mode (the default, and what a fresh clone uses) it answers from `ledger/<model>.jsonl` and raises `LedgerMiss` if the call was never recorded; it never makes a silent live call. In `live` mode it replays when the call is recorded, otherwise calls the model (at most two requests: one retry for malformed output) and appends the result, failures included. The ledger key hashes the model, settings, prompt version, output schema and packet, so changing any of them forces a new recording. `factory.py` reads `config/llm.toml` and sends only the settings listed there (a cloud model may reject `temperature`). Callers catch `LlmUnavailable` and fall back to the rule-based proposer. The OpenAI client is imported inside `build_model`, so tests and CI need no `openai` package. To say live: the local model is not repeatable even at temperature 0, so the ledger, not a seed, is what makes a run reproducible.

### units, packets and the two reviewers (task 3.2)
`app/review/units.py` lists what a reviewer is asked about: one unit per mapped trial-balance line (43) and one per journal (20). `packets.py` builds each packet by exact join: for a journal, the totals, the period, whether each account resolves in the entity's chart, the account balance before and after the line (in file order, as detector D07 reads it), and the ids of journals with the same lines or the mirror-image lines. Free text enters only as a quoted string. A packet never carries a detector verdict. `app/review/verdict.py` is the shared base of every answer: one boolean per risk category and `risk` computed in code, so a model cannot say "no risk" while flagging a category. The journal reviewer has seven categories; the mapping reviewer three plus a `better_group_code` whose allowed values are generated from the chart of accounts. Only these two reviewers are built; invoices and FX lines are decided by rules (detectors D09 to D11), so a model adds nothing there. The prompt version of each reviewer is part of the ledger key.
