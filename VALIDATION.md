# VALIDATION

Nine mistakes the AI tool made, how each was caught and the commit that fixed it. Every hash was checked with
`git cat-file -t` and is a commit in this repository.

| # | What the AI got wrong | How it was caught | Fix | Commit |
|---|---|---|---|---|
| 1 | Staged the supplied data files before `.gitattributes` existed, with line-ending conversion on, so 12 CSVs were stored with different line endings. Its own check read the working tree, so it said "bundle intact" while the commit was wrong | Hashing the committed files (`git show HEAD:path`) against `config/bundle_manifest.sha256`: 12 of 15 differed | Re-stored the files byte for byte; the pre-commit hook now rejects any staged data file whose hash differs | `4793eb7` |
| 2 | In the India investment elimination, translated the owners' share of pre-acquisition net assets at the closing rate. Policy 2 says historical rate. A plug account hid the gap and no reported figure moved, so the tests stayed green | A second session reviewing the diff | Used the acquisition-date rate and added a test; every control figure is unchanged | `111ae0b` |
| 3 | Applied the UK 2310 remap to 2300 as a quiet assumption on a 180,000 GBP revenue item | Review: "never guess" argues for a decision a person signs | Moved to `config/overrides.toml` as an open override with the effect of reversing it | `9d5326c` |
| 4 | An invariant compared a 50-digit `Decimal` to exactly zero, so legitimate rates such as a 1.4000 closing rate failed the run | A Hypothesis property test found the minimal case | The invariant uses the same 0.000001 tolerance as the other checks; a regression test was added | `570e9e0` |
| 5 | Called the oracle "independent", though it shares the method and the assumptions with the pipeline. Agreement shows wiring, not accounting | Second-session review | Reworded everywhere as "a second implementation of the same method" | `d94f14e` |
| 6 | Computed an expected intercompany difference by hand wrongly (21,246.28; the right figure was 21,292.28) | The new tests failed and I recomputed it | Fixed the expected values; the code was right | `69c74f6` |
| 7 | One shared word counted as a name match ("costs", "reserve", "stock"), giving six false alarms on clean mappings | Printing the flagged units before trusting the fallback | A match needs two shared words | `fdfaaad` |
| 8 | Wrote `NORTHWIND_MODEL` into `.env.example` and the docs, but no code read it | Writing the switch test: a grep found no reader | The model name now comes from the variable, and the ledger is named from the model | `8f7c001` |
| 9 | `from openai import AsyncOpenAI` passed locally, where the extra package was installed, and failed `mypy` on CI, so pytest never ran | CI, reproduced in a clean dev-only environment | The client is loaded by name inside `build_model` | `bc433ab` |
| 10 | Left the old output in place when an input file was re-uploaded after a run finished. A reviewer could then mark the old files reviewed and export them as Final | My own review of the finished code: I ran the case and the export said Final with the old goodwill | A changed input deletes the output and returns the run to Scan, with a test | `420cda9` |

## What was checked by hand

I re-derived these from the raw files in a script that imports nothing from `app/`, and each matched the control
figures to 0.01: `group_revenue`, `group_profit`, `profit_nci`, `nci_closing`, `goodwill_closing`,
`intercompany_difference`, `total_assets`, `total_equity`, `translation_reserve_movement` and the journal counts
(15 posted, 3 rejected, 2 held). I also set the GBP/USD closing rate to 1.30 and checked that goodwill, NCI, the
intercompany difference and the 7300 line moved by the amounts I computed by hand, while revenue and `profit_nci` did not.

The golden file `tests/golden/handcalc.json` was written by the AI tool. It has now been re-derived by a second AI
session, not by a person, and its `review_status` says so.
