# Code guide

A plain-English guide to the repository. It describes what exists now.
Current state: the engine, the orchestration, the AI review and reasoning layers and the review UI are built.

## Run and test

```bash
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest
python -m ruff check .
python -m mypy app
python run.py consolidate         # exit 0 done, 2 input rejected, 4 paused at the review gate
```

## What each top-level folder is for

| Folder | Role |
|---|---|
| `Northwind_TakeHome_v2/` | The supplied brief and data. Never edited. |
| `app/` | The application. |
| `config/` | Hand-edited TOML settings, and `bundle_manifest.sha256`, the SHA-256 of each supplied data file. |
| `tests/` | Structure, architecture and bundle tests, then unit, API, golden, perturbation, property, red-team and eval folders. |
| `ledger/`, `output/`, `transcripts/` | Recorded AI calls, a reviewed sample run, and AI session records. |

## How `app/` is divided

The split exists to keep AI output away from numbers.

- `core`, `parsers`, `detectors`, `verification`, `writers`, `domain` touch numbers. They import no AI, web or
  model code.
- `agents` holds every AI reader and none imports `core`, so a reviewer can read evidence but cannot calculate.
  `agents/journal_reviewer` and `agents/mapping_reviewer` are the per-unit reviewers; `agents/review` builds their
  evidence packets and grounds their answers; `agents/reasoning` is the read-only layer with three checkpoints and an
  explain step. The two grounding modules stay apart on purpose: `review/grounding.py` checks a verdict's risk flags
  against a packet, `reasoning/grounding.py` checks claims about cited lines and calculation ids.
- `llm` is the only place that imports a model library.
- `db` is the only place that uses `sqlite3`.

`tests/test_architecture.py` reads every source file with Python's `ast` module and fails if one of these rules is
broken. It also tests its own checker on small snippets, so it cannot pass by checking nothing.

## What the three tests prove

- `test_structure.py`: `app/` contains exactly the files in the structure plan (no missing, no extra), every folder is
  a package, each agent folder has its four files. There are two agents, the journal and the mapping reviewer.
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
`app/db/connection.py` opens SQLite and applies `schema.sql`; every JSON column has a `json_valid` check, so a malformed document cannot be stored. The service files each own one table family: runs, findings (upsert by key), and origin rows with traces. A reviewer's decision is stale when its evidence hash changes; decisions live in the run folder (`decisions.json`), and the model ledger is a file under `ledger/`, not a table. The database is disposable and rebuilt on every run.

### parsers (task 1.3)
Each input file has a contract in `app/parsers/contracts.py` (columns, decimal and date columns, allowed values). A file that breaks it raises `ContractError` with the file, line and reason. Only outer whitespace is trimmed, so `0031` stays text. `tb_adapters.py` reads the three layouts (debit/credit columns, one signed balance, amount plus Dr/Cr) into one `LedgerLine`, chosen from the header; an unknown header blocks that entity. `fx_rates.py` parses the direction of each rate from the convention column and answers in GBP terms: the product rule for GBP/INR is in `FxTable.units_per_gbp`, and a rate the file does not give returns None. `journals.py` keeps the line each journal and memo starts on, so a finding can point at `adjustments.json:112`.

### detectors (task 1.4)
Each detector is a function from a `Context` (inputs, policy, assumptions) to findings. `registry.run_all` runs all fifteen and merges findings with the same key. D01 and D03 check balance; D02 checks mappings (including the exact-name rule that catches UK 2310 Deferred income mapped to Revenue); D04 to D07 check journals (period, duplicates, accounts through the entity map, reversals past zero); D08 needs rates; D09 to D11 tie files together; D12 scans free text; D13 notes the tax step and identical months; D14 flags exact duplicate rows; D15 flags a rate far from its neighbours or from the rate a booked amount implies (amber, tolerances A14 and A15 in `assumptions.toml`). Findings never change a number: the consolidation reads them only to decide a journal disposition (task 1.6).

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
The investment-elimination balance check in `eliminate.investments` can never fail: account 3300 is a plug in both entries, so each entry balances by construction. It stays as a guard against a later edit, not as evidence. `core/lineage.py` lists the postings every consolidated balance is made of and builds a trace per figure. `app/writers/` writes the required files: values are rounded to 2 decimals only there (`round_tree`). `consolidated_tb.csv` and `eliminations.csv` cite `file:line` for every row. `run_manifest.json` records input, policy, assumption and code hashes plus a hash of every other output, so two runs on the same inputs can be compared byte for byte. `run.py consolidate` runs everything and stores findings, origin rows and traces in `.northwind/run.db`; `run.py trace goodwill_closing` (or an account such as `1100`) walks a result down to the source rows; `run.py check` verifies the data bundle and the policy binding.

### input validation (the bouncer)
Impossible inputs stop the run before any figure with a `ContractError` naming file, line and column. `finite_decimal` in `contracts.py` refuses text, NaN and infinity. `fx_rates.py` refuses a rate that is empty, zero or negative, and a second row for the same pair, rate type and date (in either direction), whether it repeats the first or conflicts with it. `tb_adapters.py` and `journals.py` refuse a line with both debit and credit filled, and a journal amount that is not a decimal. `check_percentage` accepts above 0 and up to 100 (the UK is 100) for `ownership_pct` and for the interest in the acquisition note. `ranges.py` checks, against the policy period, India's months, invoice dates, and that the closing and opening rates are dated at the year ends; journal dates are not checked there because a journal outside the year is a finding (JE-017). Map files hold no amounts, so there is nothing to check in them. The command line prints `input rejected: <place>: <reason>` to stderr and exits 2 (a paused run exits 4); the API answers 422 with the same text. A rate that is possible but wrong (x100, an inverted pair) is not rejected: D15 flags it amber and the run continues. `tests/perturbation/test_bad_inputs.py` and `test_rate_typos.py` are the table of cases with exact outcomes.

### run log (task 1.14)
`app/utils/logging.py` writes one JSON line per event to `.northwind/logs/`. Each line has `run_id`, `stage` and `event`; finding events carry the finding key and gate events the check name and result. Every stage node appends to the same file, started at intake and named in `RunState.log_file`. Timestamps live only in this log, so the required outputs are byte-identical between runs while the logs differ.

## Wave 2 module notes

### overrides and the review queue (task 2.2)
`config/overrides.toml` holds human decisions. Each one stores an `evidence_hash`: the hash of the mapping row and the trial balance row the reviewer looked at. `services/overrides_service.py` classifies every override on each run: `applied` (approved, evidence unchanged), `open` (not yet signed off, still applied and reversible), `stale` (the evidence changed, so it stops applying) or `rejected`. `build_context` feeds only applied and open ones into the run. `review_queue` lists open and stale overrides first, then every flagged or blocked finding; notes are left out. To say in the live session: a decision is only valid for the evidence it was made on, so an input change puts the item back in front of a person instead of silently carrying an old approval forward.

### the LangGraph workflow (task 2.1)
`app/orchestrator/` runs five stages: intake, analyse, resolve, consolidate, export (`nodes.py`). `graph.py` wires them; after analyse, `edges.after_analyse` sends the run to resolve only if an override is open or stale. Resolve calls `interrupt()`, so the run stops and its place is saved in `.northwind/checkpoints.db` under the thread `run-<input hash>`. The input hash covers the 15 data files and `policy.toml`, `assumptions.toml`, `overrides.toml`, so approving an override gives a new run id and a new thread; a paused thread is never reused for a different configuration. `python run.py resume --thread T --approver NAME --approve mapping:UK:2310` answers it from another process: the answer is written into `config/overrides.toml` with the evidence hash and the run continues. The state holds only paths, the run id, status and open item keys; each node rebuilds what it needs from the files (about 20 ms), which keeps the checkpoint small and the answer to "where did this number come from" in one place. LangGraph reruns the interrupted node from its top on resume, so nothing with a side effect happens before `interrupt()`.

### the plain runner (task 2.3)
`runner_plain.run_plain` calls the same node functions in order, with no LangGraph. `python run.py consolidate --engine plain` uses it. With an override waiting and no answer it stops at the human gate (status `awaiting_review`), as the graph does. The tests run both runners on the same inputs and compare the SHA-256 of every output file, including `run_manifest.json`; they also compare a graph that was paused and resumed against a plain run that was given the same answer. To say live: if LangGraph will not install on a reviewer's machine, the plain engine gives the same bytes.

### whatif, impact and diff-inputs (task 2.4)
`services/whatif_service.py` copies the input folder to a temporary directory, applies the change and runs the whole consolidation on the copy; the supplied files are never written (a test hashes them before and after). `python run.py whatif --patch fx_rates.csv:6.rate=1.30` sets one cell (line numbers count the header as 1, line endings are kept); `--append "fx_rates.csv=GBP,SGD,closing,1.7300,2024-12-31,SGD per 1 GBP"` adds a row; `--set je017=post` flips an assumption for that run. The output is the control figures that changed and the group accounts that moved. `impact fx_rates.csv:6` nudges the row's rightmost number by 1% and prints what moved: it is measured, not read from a diagram. `diff-inputs OLD_FOLDER` lists the files and line numbers that differ from an older copy. To say live: change an input, predict which figures move, run whatif, compare.

### perturbation and property tests (task 2.5)
`tests/perturbation/` changes one input at a time on a copy and checks two things: the invariants and the oracle still hold, and the figure moves by the amount worked out by hand (US revenue +1,000 USD gives +782.47 GBP at the 1.2780 average). Cases: US revenue, four rates, a new SGD closing rate, an intercompany invoice, an unbalanced trial balance (every figure null with a reason), posting JE-017, a missing rate, and a closing rate that leaves a repeating decimal. `tests/property/` uses Hypothesis to change five rates (60% to 160%) and a balanced US posting at random and requires every non-oracle check to pass. Two things these tests taught us, kept as tests: the full-year INR average feeds no figure (India is translated at the H2 average, policy 2), and the oracle cannot follow an SGD closing rate (it keeps the bank at booked value), so it disagrees by exactly 111.39 when one is added. The property test found a real defect: the elimination-balance invariant compared a 50-digit Decimal to exactly zero, which fails by about 1e-48 at some rates; it now uses the 0.000001 tolerance the other invariants use.

### status sidecar and the strict control figures check (task 2.6)
`control_figures_pb.json` holds the 12 keys, each a number or `null` (`journals` is posted, rejected and held counts). The reason for a `null` and the open items behind a provisional figure live in `control_figures_status.json`, so the required file keeps the shape the brief asks for. `tests/unit/writers/test_control_figures_schema.py` validates the file with a strict Pydantic model (no extra keys, no numbers as strings, no booleans) on the supplied data and on a blocked run, and checks that every `null` has a reason and every provisional figure names its open items.

## Wave 3 module notes

### the model adapter and ledger (task 3.1)
`app/llm/` is the only place that imports `pydantic_ai`. `client.run_structured` makes one typed call. In `replay` mode (the default, and what a fresh clone uses) it answers from `ledger/<model>.jsonl` and raises `LedgerMiss` if the call was never recorded; it never makes a silent live call. In `live` mode it replays when the call is recorded, otherwise calls the model (at most two requests: one retry for malformed output) and appends the result, failures included. The ledger key hashes the model, settings, prompt version, output schema and packet, so changing any of them forces a new recording. `factory.py` reads `config/llm.toml` and sends only the settings listed there (a cloud model may reject `temperature`). Callers catch `LlmUnavailable` and fall back to the rule-based proposer. The OpenAI client is imported inside `build_model`, so tests and CI need no `openai` package. To say live: the local model is not repeatable even at temperature 0, so the ledger, not a seed, is what makes a run reproducible.

### units, packets and the two reviewers (task 3.2)
`app/agents/review/units.py` lists what a reviewer is asked about: one unit per mapped trial-balance line (43) and one per journal (20). `packets.py` builds each packet by exact join: for a journal, the totals, the period, whether each account resolves in the entity's chart, the account balance before and after the line (in file order, as detector D07 reads it), and the ids of journals with the same lines or the mirror-image lines. Free text enters only as a quoted string. A packet never carries a detector verdict. `app/agents/review/verdict.py` is the shared base of every answer: one boolean per risk category and `risk` computed in code, so a model cannot say "no risk" while flagging a category. The journal reviewer has seven categories; the mapping reviewer three plus a `better_group_code` whose allowed values are generated from the chart of accounts. Only these two reviewers are built; invoices and FX lines are decided by rules (detectors D09 to D11), so a model adds nothing there. The prompt version of each reviewer is part of the ledger key.

### grounding, fallback and the review service (task 3.3)
`app/agents/review/grounding.py` checks each claim in a verdict on its own against the packet. `journal_facts` proves unbalanced, outside period, account not in the chart, duplicate, mirror-image and exceeds-balance from numbers; a claim the packet does not support is dropped with a reason and the others stand. Wording claims (`text_contains_instruction`) cannot be proved from numbers: they are verified when the D12 lexicon matches and otherwise kept as `unverified`, which never counts as risk. A mapping claim needs a proposed account that exists in the chart; a name mismatch also needs the local name to share two words with that account's name and more than with the current one (one shared word, like "costs", gave six false alarms in a first try). `fallback.py` answers from the same exact facts when no recorded model answer exists, so a ledger miss degrades to rules, not to an error. `services/review_service.py` runs both reviewers over all 63 units: replay or record, ground, fall back. The result is advice and changes no figure (policy 2). On the supplied data the rule-based proposer flags exactly the six defective journals (JE-006, 009, 014, 016, 017, 019) and one mapping (UK 2310).

### eval harness and injection tests (tasks 3.4 and 3.5)
`tests/evals/` measures agreement with deterministic checks on labels the author wrote; it is not an accuracy figure. The labels were written by the same AI tool that wrote the rule baseline, and the baseline shares its predicates (`journal_facts`, `mapping_facts`) with grounding, so the rules scoring well is partly by construction. It scores reviewer results with set arithmetic only, no judge model: recall of labelled defects, false alarm rate of verified claims, the share of claims grounding dropped, and exact matches per unit. Labels for the supplied data are in `labels.py` (six journals, one mapping, everything else clean); `seeds.py` adds seven journal and eight mapping units with one thing broken each, labelled by construction, to measure recall on cases the data does not contain. `python -m tests.evals.record --live` runs everything against the configured model, appends to the ledger, writes `.northwind/eval_results.json` and prints a few summary lines; without `--live` it replays. The rule-based proposer is the baseline: it finds every labelled journal defect from numbers, but cannot read the JE-006 memo's wording. `tests/redteam/` shows that the memo cannot change a disposition, a figure or a finding: removing it changes nothing, and a recorded answer from a model that obeyed it (all false) leaves the engine untouched while the review service marks the unit `missed=('unbalanced',)`, the model disagreeing with the rules.

### the lexicon policy reader (task 3.6)
`app/parsers/policy_text.py` now also reads `group_policies.md` with a lexicon: for eight policy choices (translation of assets and liabilities, income and expenses and equity, monetary items, NCI measurement, goodwill translation, intercompany elimination, journal posting) it finds the sentence in the right clause and matches a few ways of saying each value ("closing", "year-end", "reporting date"). Each reading carries its clause number and the quoted sentence. A sentence it cannot read gives `None` with a reason, and one that matches two values is ambiguous: never a guess. `compare` sets the readings against `config/policy.toml`, and `run.py check` now reports any difference. The hash binding still decides whether a run may continue; the lexicon says why the approved config no longer matches a changed text. An LLM reader for clauses the lexicon cannot read is stretch work and not built.

### the model switch and `run.py review` (task 3.7, local part)
Everything model-specific is in `config/llm.toml`: the model string (`ollama:`, `openai:`, `google:`, `anthropic:`), its settings (leave the table empty for a cloud model that rejects sampling parameters) and the ledger file. To switch: set `model` and `ledger`, put the provider's key in the environment (never in the repo), and run `python run.py review --live` once to record that model's answers; commit the new ledger file. The ledger key includes the model and settings, so the local ledger can never answer for a cloud model (a test proves a miss, then the rule fallback). `run.py review` prints the verified, unverified and missed claims per unit and how many units a model answered. Running it changes no figure: a test hashes the figures before and after. The cloud recording is described in the next two sections.

### running a cloud model safely (final development run)
**Add the key.** Copy `.env.example` to `.env`, paste the key after `OPENAI_API_KEY=` and set `NORTHWIND_MODEL=openai:gpt-4o-mini` (or export both in the shell). `app/utils/env.py` loads `.env` without overriding a variable that is already set. The key is read only from the environment. `scrub()` hides key-shaped text (`sk-...`, bearer tokens, the exact value of a key variable) before anything is written to the ledger or put in an error message, and the pre-commit check rejects staged text that looks like a key (a test value is marked `FAKE`). `.env` is gitignored.

**Switch the model.** `NORTHWIND_MODEL` changes the model and nothing else: the ledger file is named from the model (`ledger/openai-gpt-4o-mini.jsonl`), so the local ledger is never touched, and the sampling settings come from the empty `[llm.cloud_settings]` table (determinism comes from the ledger; `seed` is documented as best effort). The output cap is sent as `max_completion_tokens`, the name the current API expects. Without a key a live run stops at once with a plain message.

**Run it.** First `python -m tests.evals.record --live --smoke`: one journal and one mapping unit, then the tokens and cost. Then `python -m tests.evals.record --live` for the rest (units already recorded are replayed, never sent again). Both print about ten lines and never the raw answer. `python run.py review --live` records for the whole run, and `python run.py review --cost` prints the report.

**Limits.** Each request times out after `request_timeout_s` (60). A call is at most two requests (one retry for a malformed answer). A 429 for rate and any 5xx are retried twice after a 2 s and an 8 s wait; a timeout is not retried. A 401, a 403 and a 429 that means no credit (`insufficient_quota`) raise `LlmStop`: the batch ends with the units left counted. After five live calls in a row fail or are unavailable the breaker stops the batch the same way. There is no dollar cap, so the number to watch is the call count in the summary.

**Cost report.** `config/pricing.toml` holds the price per million tokens with its source URL and the date it was read; it stays ASSUMED until someone checks the page. Each recorded call stores its tokens and its cost (null with a reason for a model without a price). `review --cost` prints calls, tokens, recorded cost and new cost per agent: a replay shows 0 new cost and the cost recorded earlier. Costs go to the screen and the run log, never into the 12-figure outputs, which stay byte-identical (a test runs the figures with the local ledger, a fake cloud ledger and no model).

**What the docs said, 2026-11-18.** `gpt-4o-mini` supports `json_schema` structured output; strict mode needs every property required and `additionalProperties: false`, which pydantic-ai's OpenAI schema transformer produces (checked on both reviewer schemas). The model page marks the dated snapshot `gpt-4o-mini-2024-07-18` as deprecated while the alias is still listed: record early and expect to change the model string later.

### results of the local model (task 3.4)
Recorded with `qwen3:4b-instruct-2507-q4_K_M` (78 units, ledger `ledger/qwen3-4b-dev.jsonl`, 83 lines; one seeded unit, `SEED-J-balanced`, timed out twice and is answered by the rule fallback). After grounding:

| Reviewer | Units | Recall | False alarms | Claims dropped by grounding |
|---|---|---|---|---|
| Local model, supplied data | 63 | 0.33 | 0.00 | 0.62 |
| Local model, seeded | 14 | 0.17 | 0.00 | 0.71 |
| Rule-based baseline, supplied | 63 | 0.89 | 0.00 | 0 |
| Rule-based baseline, seeded | 15 | 0.46 | 0.00 | 0 |

Read these as agreement with those checks, not accuracy. Part of the dropped share measures how strict the two-word name rule in grounding is. The model reliably found duplicates, the unbalanced journal and mirror images. It missed all three out-of-period dates, the exceeds-balance case and the unknown account, and its mapping claims mostly failed grounding (10 name-mismatch claims dropped, 9 real ones missed). Grounding removed every false claim (false alarms 0.00 after it), which is what it is for, but the cost is low recall: a 4B model is a weak second opinion here and the rules do better on every category they can compute. The rules cannot read wording, so the model's value is limited to cases like the reworded memo. Prompts were not tuned further (journal prompt on its second version, mapping on its first); the result is a finding, not a target. The sample is small and the labels are mine.

### results of the cloud model (task 3.7)
Recorded with `openai:gpt-4o-mini` (78 units, 77 calls, ledger `ledger/openai-gpt-4o-mini.jsonl`; 34,525 input and 5,388 output tokens, about $0.008 at the ASSUMED prices in `config/pricing.toml`). Every unit was answered by the model, none by the fallback. Same wording rule as above: agreement with deterministic checks on author-written labels, not accuracy.

| Reviewer | Units | Recall | False alarms | Claims dropped by grounding |
|---|---|---|---|---|
| Cloud model, supplied data | 63 | 0.56 | 0.00 | 0.80 |
| Cloud model, seeded | 15 | 0.29 | 0.00 | 0.60 |
| Local model, supplied data | 63 | 0.33 | 0.00 | 0.62 |
| Rule-based baseline, supplied | 63 | 0.89 | 0.00 | 0 |
| Rule-based baseline, seeded | 15 | 0.46 | 0.00 | 0 |

On the six supplied journals the cloud model found five of the six defects (unbalanced, two duplicates, unknown account, out-of-period) and missed the exceeds-balance case. Its mapping answers were mostly dropped by grounding. It is a better second opinion than the 4B model, and still below the rules on everything the rules can compute. Prompts were not tuned after the first recording.

For JE-006 the model said the entry is unbalanced and did not follow the memo; it did not flag the memo as an instruction (`text_contains_instruction` false), which the D12 lexicon does. A test replays that real answer and asserts that dispositions, the 12 figures and the findings are unchanged; another test shows they are identical with the local ledger, the cloud ledger and no model.


## The review page (wave 4)

### what it is
`python run.py serve` starts FastAPI on 127.0.0.1:8000 and serves `frontend/` at `/ui`. It adds no accounting and no model logic: every route calls a service that already existed. Say this in the live session: the page is a window onto the CLI's own paths, and a test proves it shows the same 12 figures as `run.py consolidate`.

### the pieces
- `app/services/registry_service.py`: one folder per run under `.northwind/runs/<id>/` (`data/`, `config/`, `output/`, `run.db`, `checkpoints.db`, `logs/`, `run.json`). The config files are copied per run, so approving an override in the page edits that run's copy, never `config/overrides.toml`. The id must match a strict pattern before it touches the disk.
- `app/services/upload_service.py`: the 15 expected names, a 1 MB limit, and one existing parser per file. A body is checked in a scratch file and stored only if it passes, so the error shown on a row is the error the run would hit. Uploaded text is data: it is parsed, never run, and shown with text nodes.
- `app/services/pipeline_service.py`: `analyse` is the same graph as `run.py consolidate` (it pauses at the review gate), `decide` is `resume_graph`, `review_view` collects findings, dispositions, the queue and the advice, `build` re-runs the engine's 20 checks.
- Advice is replayed from the ledger only. A unit with no recorded answer falls back to the rules and the page says "not recorded". A test makes `build_model` raise and the review route still answers.
- `app/services/results_service.py`: reads `control_figures_pb.json` and `control_figures_status.json` (a null shows its reason), builds the zip (only names in the run's own output folder, plus `run_manifest.json`), and compares two runs with `diff_inputs` and `impact`.
- `app/routes.py`, `app/routes_results.py`, `app/api_models.py`, `app/main.py`: thin endpoints, strict request models, handlers that turn `UnknownRun` into 404, `NotReady` into 409 and bad input into 422.

### the input workbench (item 1: rows and explain)
- `app/services/rows_service.py`: a source file as labelled rows. A CSV record, a journal in `adjustments.json` (at the line of its `"id"`, the line the journal findings cite) or a non-blank line of a markdown file is one row. A finding belongs to the last row starting at or before its cited line.
- `app/services/inputs_service.py`: `rows_view` puts each finding on its row; `row_explain_service.explain_row` adds the rule in plain words, the policy clause, the evidence cells and the recorded AI view. The AI view is attached to a finding only for D02 to D07 and D12, because the reviewers read journals and trial-balance mappings only; a row of a mapping file or a journal also states what the AI looked at when no rule found anything.
- `app/services/rule_text.py`: one sentence and one policy reference per detector, and which reviewer actions the workbench offers on it.
- Endpoints: `GET /api/runs/{id}/inputs/{file}/rows` and `GET /api/runs/{id}/inputs/{file}/rows/{line}/explain`. No model is called.

### scan progress (item 2)
- `app/orchestrator/nodes.py`: the analyse stage now logs one `file scanned` event per file (with its finding count) before the `findings` event. The log is not an output, so no output hash moves.
- `app/services/scan_service.py`: `GET /api/runs/{id}/scan` reads the newest log of the run: a file with an event is scanned, one without is waiting, one not uploaded is missing; the scan is finished when the `findings` event exists. The Scan page starts the analysis and polls this every 300 ms, so the bar shows what the log holds.

### home and upload (item 3)
- Home (`#/`): "Continue a run" takes a run id and opens the run at its next step (an unknown id says so); "Create a new run" takes a name and an optional sample start. The runs list stays below it.
- Upload: each of the 15 files has its own chooser, so files go in one at a time. The mark comes from the server: Uploaded (stored and valid), Rejected (the contract's reason is shown and nothing is stored) or Not uploaded. Next stays disabled until all 15 are in.

### the input workbench (item 4)
- `frontend/workbench.js` is the Review inputs step: files on the left with an open/total badge, rows in the middle (red blocking, amber flagged, grey noted; each row also says its review status in words), and a drawer for the selected row. The page replaces the old review step; the recorded AI review in full is still there, under the rows.
- `app/services/decisions_service.py`: the reviewer's decisions, an append-only `decisions.json` in the run folder (finding key, pass or override, reviewer, note, evidence hash, time). The evidence hash covers the finding and the row's exact values, so a decision made on a row that later changes reads as stale. Open and stale are worked out when read.
- `app/services/review_actions_service.py`: `POST /api/runs/{id}/inputs/{file}/decisions`. Pass acknowledges and moves no figure; passing a finding about a held journal (D06, D07) also closes that held item, which the engine already treats as reviewed and out of the figures. Override is refused unless the table in `rule_text.py` allows it, and the only override with an engine mechanism is the mapping one (D02, while it waits). D06 and D07 are allowed by the spec table but the engine has no mechanism, so they are acknowledge-only for now and the drawer says so.
- A file's badge counts open and stale findings out of all findings on it. Notes need no decision, so a file with only notes reads "Notes only", not "Reviewed".
- Say in the live session: every number on this page is the engine's; the page records who looked and what they decided, and a click can never silently change money.

### generate output (item 5)
- `app/services/generate_service.py`: `POST /api/runs/{id}/generate` works as soon as the run is scanned. With every item answered it is the normal build. With items still waiting, it runs the same consolidate and export nodes without the human gate, so the files are what the engine produces with nothing applied that nobody signed off, and the output is a Draft. The run keeps its status (awaiting review); `generated_for` stores the input hash the Draft was made on, so results and files open for it, and close again if an input or the config changes.
- `GET /api/runs/{id}/unanswered`: the engine items still waiting and the findings nobody has passed or overridden (notes need no decision). A held journal and its D06 or D07 finding are one problem and are counted once. Passing a finding clears it from this list; it does not move any figure. The Draft banner on the later pages and the Generate page read this list.
- Test worth quoting: the Draft's twelve control figures equal the figures of a run whose held items were approved, because held journals stay out of the figures either way.
- Final or Draft is decided by sign-off (see "Review UI: the seven stages" below) and written into `signoff.json` in the zip.

### the seven stages
The stages are the ones in "Review UI: the seven stages" at the end of this guide: upload, scan, review inputs, choose outputs, generate, review outputs, done. Results, what-if and compare are one page reached from Done. A what-if patches a copy of the run's data (`file:LINE.column=value`, file must be one of the 15) and builds a new run beside the old one.

### limits to state honestly
One user, no login, no concurrency control: it is a local tool. What-if edits one cell; assumption overrides are not offered. `group_policies.md` is checked only for being readable; the policy binding is still enforced when the run starts. The gate detail text is shown tidied (Decimal reprs and long fractions shortened) in the page only.


### the redesign (still no new accounting or model logic)
- Look: `frontend/style.css` is hand-written, a system font stack, light and dark through `prefers-color-scheme`, visible focus, colours chosen for WCAG AA contrast. The header shows the run name, status and current step; a stage bar in the header shows each stage as done, current, needs you (blocked) or not yet. The "runs locally" line is the footer note.
- Numbers: `frontend/format.js` shows GBP with separators and two decimals in right-aligned tabular numerals. The server sends money as text and the page never turns it into an exponent. A null reads "Not determinable" with its reason in a callout; a provisional figure has a badge with the open item as its tooltip and as a callout (touch screens cannot hover).
- Issue cards: `app/services/cards_service.py` writes each headline from the finding itself (amounts tidied, for example "JE-006 does not balance: debits 51,200, credits 50,000"). The memo sentence is added only when a D12 finding lies inside that journal's lines, and it says "asks reviewers to skip the check" only if the memo's own words do. The AI line is agrees, disagrees, raised no claim or not reviewed, taken from the recorded review of the same journal or account; a finding with no matching unit says not reviewed. Dropped claims come from grounding.
- AI review panel: `app/services/ai_service.py` replays the ledger (never a live call) and returns every unit with its evidence packet, the model's recorded answer, the grounding verdict, tokens and cost. Totals are sums of those rows. The panel is labelled "recorded review". Build shows the stages from the run's own log files (times are when they were logged) and then the gates; nothing is animated.
- Output viewer: `app/services/output_service.py` lists each output with rows, bytes and sha256, opens a file as tables (JSON money is read as text, 500 rows at most, 2 MB cap, download always works) and sorts the issues for a file. An issue is traced to a file only when its input `file:line` appears in that file's `source_rows` (statements: in the accounts they list; control figures: the figure named in the claim). Everything else is listed as Run-wide, never guessed onto a file. Routes: `/output-files`, `/output-files/{name}`, `/output-files/{name}/issues`, `/output-files/{name}/download`.
- States: every step shows "Loading", a retryable error, or an empty message. A step that needs a finished run explains why it is held back: paused (how many items wait, go to Review), blocked (the blocking reason) or not analysed.
- Not verified in a browser: keyboard-only use beyond visible focus.
- Waiting items: `waiting_cards` in `cards_service.py` makes one card for each open or stale override, with its reason and the effect of approve and of reject (the override's own `effect_if_reversed`). The review step draws them first, with the name field and Submit below. Held journals later became waiting items too (see "Held journals" below).
- Gate: `require_done` refuses every step after review with 409 naming the undecided items, so results and build cannot show a figure while an item feeding it is open. The page refuses an empty or nameless submit and disables Next until nothing is waiting. Open and stale overrides block, and so does a held journal nobody has answered (see "Held journals" below).
- Money on the API: `results_service._json` reads every non-integer number in an output file as a two-decimal string, so no float crosses the boundary (counts stay integers). `format.js` hands those strings straight to Intl.NumberFormat, which formats a decimal string exactly.
- Safety: `create_app` adds TrustedHostMiddleware (127.0.0.1 and localhost only) and every error handler, including a catch-all 500, passes its text through `scrub`, which keeps a file name and drops the folders. Tests use base_url http://127.0.0.1.
- AI line on a card: a unit that was reviewed and not flagged reads 'Reviewed by the AI, not flagged'; 'Not reviewed' is only for a finding with no unit. A D12 memo finding is tied to the journal whose lines hold it (JE-006), and the AI's other claims about that journal (unbalanced) are not counted as agreement on the text, since free text cannot be proved from the packet.
- Output views: file tables use the same GBP formatting as the figures table; a list in a JSON file is one cell with a line per entry; provisional figures that share a reason share one callout; the figure headline pattern had lost its word boundary (a stray control character), which left 'Sgd_bank_gbp' unnamed, now fixed and tested; dropped-claim text says 'the supplied data' not 'packet'. Runs can be archived (hidden, not deleted) and restored from the runs list.
- Switching output files was slow because each switch re-ran the engine and the ledger replay for the issue cards (about 70 ms), then fetched the file list again, and asked for the file and its issues one after the other. Cards are now kept per run until issues.json or the ledger changes (about 7 ms after the first), the file list is read once per run, and the two requests go out together.
- D02 nature rule (`_nature_problem` in detectors/mapping.py): a mapped line whose own name reads as a liability (deferred, accruals, payables, loans, provisions) but maps to a non-liability group account, or reads as income but maps to a non-revenue one, is flagged and left as supplied. It needs no exact name match, so 'Deferred income (current)' is caught. It never remaps, since a remap needs a stated assumption. It is silent on the supplied data apart from the existing 2310 finding.
- Held journals: a journal the rules hold ("needs a human") is a waiting item as `journal:JE-016`. Its card offers Approve (recorded as accepted as held) and Reject (recorded as disputed). Neither moves a figure, because a held journal is not posted either way; the decision is stored with the approver's name in the run's `held_decisions`. This is an ASSUMED reading of the brief, logged in DECISIONS_LOG. The engine and the command line are unchanged; the pause is applied in `pipeline_service._with_held`, so a run with an undecided held journal is `awaiting_review` and the same 409 gate covers it.


## The reasoning layer (advice only)

Principle: code calculates, the model reads and explains. The layer sees everything and can change nothing: no figure,
no disposition, no rule. It lives in `app/agents/reasoning/` and never imports `app/core` (a test checks this). It runs on a
cloud model only; with the local model `review --reasoning` prints "AI review not available" and every rule and figure
is unchanged.

**Calculation records.** `app/core/calculations.py` builds, after the run, one record per consolidated row and per
control figure: a formula text, its inputs with their `file:line` (or `calc:<id>` when the input is another record) and
the result. `app/verification/recalc.py` re-runs the formula from the inputs with a small evaluator (names, whole
numbers, `+ - * /` only) and a test fails if it does not equal the result. The Unknown SGD figure has no record.

**Three checkpoints.**
1. `reader.py`: every line of every input file, in chunks of 40 lines per file, with the file's plain meaning
   (`meanings.py`). The model answers with flags from a fixed menu (`schema.py`).
2. `calc_review.py`: after the engine, one call per calculation record; the model judges sign, size and fit.
3. `investigator.py`: for each concern, the model follows the result back with read-only tools and reports a chain.

**Grounding and the two tiers** (`grounding.py`). A claim is dropped when its `file:line` or calculation id does not
exist, or when a quoted text or any number in its reason is not in what the model was shown. A claim that stands is
*verified* only when code can prove it (an impossible date, a line with no letters, a sign on a figure that must be
positive, or a fact a detector already confirmed); otherwise it is a *suspicion*: shown, never counted, never gating.

**Contradicted claims** (`contradiction.py`). Before a claim is kept as a suspicion, code tries to prove it false and drops it
as "contradicted" if it can: a date claim when every date on the line is valid; a rate claim when the rate is inside the
D15 tolerance of its pair; a nature claim when the name and the group account it maps to share a nature; a missing-name
claim on a line that has a name; a sign claim on a non-negative figure whose result is not negative. A suspicion therefore
means "the code could not tell", never "the code looked and disagreed".

**Seeded-fault evaluation** (`tests/evals/seeded_faults.py`). Plants six faults in a copy of the data (closing rate x100,
a journal amount typo, a map row moved from Revenue to Tax, a TB label that contradicts its map name, a journal year
typo, a duplicated intercompany invoice), finds the changed lines by diffing, runs the reasoning layer on the copy and
reports per fault hit or miss, plus false alarms (kept claims on lines no fault touched). A fault is hit when a kept
reader claim names one of its lines, or a kept calculation concern is built from one. It also lists which rule findings
point at each fault's lines (journal findings carry no line number, so that column understates the rules). No finding
or verdict is put in a packet; a test checks the packet keys and text. `python -m tests.evals.seeded_faults --live`
calls the configured model and writes `.northwind/seeded_faults/result.json`; the tests use fake models.

**Explain step** (`explain.py`). For a finding the rules already raised, the model writes why it matters (`cause`) and a
trace to the source lines, with the same tools, caps and grounding as the investigator. It runs after detection, so the
finding is its input by design; the detection packets (reader, calculation reviewer) still hold no verdict. A test checks
the finding list is identical before and after. Not yet wired into the CLI, and not run live.

**Citation forms** (`cite_exists`). A trace step may cite what the tools print: `file:line`, `file:first-last`, a
calculation or row id with or without `calc:` or `lineage `, `account N`, `rule policy N`. An id no tool could have
returned is dropped. Before this, `calc:row:1200` and `lineage row:1200` were dropped as nonexistent (69 of 99 steps).

**Sign and the normal side.** Balances are stored debit-positive, so a credit-nature account (revenue, payables, equity)
holds a negative number. Each row record carries `normal_side` from the chart and a `storage` sentence saying so; a sign
concern on a row that sits on its normal side is dropped as contradicted. Only a balance against its normal side stays.

**Tools** (`tools.py`): `read_lines`, `find_in_file`, `get_rule`, `get_calculation`, `get_lineage`, `get_related`.
File tools take a file name from the run's own list, never a path. At most 5 calls per item, no repeated call, and
every result is returned as `quoted_data` with a note that it is data. A test lists the tools and fails on any name,
parameter or import that could write, run a command or reach the network.

**Ledger and cost** (`app/llm/tooluse.py`). A tool-using call is keyed by model, settings, prompt version, schema,
packet and tool names; the answer is stored with its tool trail, so a replay shows what the model looked at. Unchanged
units replay free and only changed units go live. `--max-units N` limits live units for a whole run (it counts units,
not dollars); five failures in a row trip the circuit breaker; an authentication error stops the run at once.

**Commands.** `python run.py review --reasoning` replays; add `--live` to record unrecorded units; add `--smoke` to send
one unit to each checkpoint.

**What to say about it.** The model is never trusted with a number: its schema has no number field and no field that
can name a decision. Hostile text in a journal memo or a map name changes no figure, disposition or rule finding (a
tested fact), a hostile rate row is refused by validation before anything reads it, and a simulated model that obeys
the text changes nothing. Figures and output hashes are identical with the layer off, on and replayed.

## Review UI: the seven stages

Changing an input after a run was analysed removes its output and sends it back to Scan (`pipeline_service.invalidate`), so nothing generated from old inputs can be reviewed or exported.
Upload, Scan, Review inputs, Choose outputs, Generate, Review outputs, Done. The stages sit in a top bar (no side rail).
- Choose outputs comes before Generate: `PUT /runs/{id}/output-plan` stores the choice (the nine files are known up front). Every file is still built; the choice decides what is reviewed and what goes in the zip.
- Review outputs (`frontend/viewer.js`): files on the left, rows in the middle, a drawer for the clicked row. The drawer shows the calculation behind a control figure or a group account, read from the run's evidence store by `GET /runs/{id}/calculation/{target}` (`calculation_service.py`). It says the figures are checked by the gates and the oracle, not by an AI agent.
- Sign-off (`signoff_service.py`): a reviewer marks each exported file reviewed against its sha256 (a changed file goes stale). The export is Final only when no input problem is open and every exported file is reviewed, otherwise Draft. The status goes into `signoff.json` in the zip; `run_manifest.json` is not touched, so the byte-identical output check still holds.
- A reviewer can also mark single rows reviewed (`POST /signoff` with a `row`); a row mark is tied to the file's hash and does not review the file. Only file marks decide Final or Draft.
- Generate lists every chosen file as building and marks each generated when the call returns; the server does not stream progress, because generation is one quick call.
