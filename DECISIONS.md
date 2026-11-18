# DECISIONS

Seven design decisions. Each has the options, the choice, the trade-off, what the AI tool suggested and whether it was
taken. The AI tool was Claude Code; it wrote most of the code and I decided what stayed.

## 1. The AI recommends, rules and people decide

- **Options:** the AI posts or holds journals itself; the AI only recommends; no AI at all.
- **Chosen:** recommend only. Every figure is computed by deterministic code on `Decimal`. A model answer is checked
  against the evidence it was shown (grounding) and can never change a figure, a journal disposition or a rule.
- **Trade-off:** slower to apply, but a wrong hold of a valid entry would misstate profit.
- **AI suggestion:** it first proposed one-way holds by the model. I challenged it and the accounting argument won.
- **Measured result:** replaying the recorded gpt-4o-mini answers, the reasoning layer hit 4 of the 7 labelled faults in the
  supplied data (the rules flag all 7) and kept 48 reader claims, 1 of them verified; 38 fall on lines no label covers
  and are shown as suspicions. So the rules are the detector and the AI layer is advice. Figures, dispositions and findings are identical with the local ledger, the cloud ledger and
  no model (`tests/unit/llm/test_switch.py`).

## 2. Three kinds of gap, three different answers

- **Options:** fill every gap with a best guess; stop the run at the first gap; treat each kind of gap differently.
- **Chosen:** a **data gap** (a value the files do not give) is `null` with a reason, as with the SGD bank, which has no
  GBP/SGD closing rate. A **method gap** (the policy is silent) takes an `ASSUMED` value recorded in
  `config/assumptions.toml` with the effect of the alternative. A **defect** (a fault in the data) becomes a finding that
  a person passes or overrides.
- **Trade-off:** more states to explain, but no figure is ever invented.
- **AI suggestion:** none recorded; the rule "never invent a value" was set in the operating instructions I gave it.
- **The three questions I emailed.** Each method gap below was put to the company, with the stated assumption applied
  until a reply changes it (one line in `config/assumptions.toml`, then the run re-executes):
  - Q1 (A1, A1b): the 20 journals are not already in the trial balances, so valid ones are posted on top, and JE-018
    and JE-020 do not overlap `in_pl_monthly.csv`. If they do overlap, India July to December profit rises by
    4,950,000 INR (about 45,921.86 GBP).
  - Q2 (A2): the investment in Northwind UK is eliminated in full against UK equity, with no UK goodwill.
  - Q3 (A3): the 20% non-controlling interest takes its share of India's translation difference; the goodwill
    retranslation difference stays entirely with the parent. A different split moves NCI and the translation reserve,
    not total equity.

## 3. The UK 2310 deferred income line is an override signed by a person

- **Options:** keep `map_uk.csv` as supplied (2310 into revenue 4100); remap to 2300 deferred income, a liability; hold
  the line out of the consolidation.
- **Chosen:** remap to 2300 and record it in `config/overrides.toml` as approved by a named person.
- **Trade-off:** reversing it adds exactly 180,000 GBP to revenue and profit and lowers liabilities by the same.
- **AI suggestion:** it applied the remap as a quiet assumption. I made it a signed override, because a guess on a
  180,000 GBP revenue item should be reviewable.

## 4. A replayable JSONL ledger of model calls

- **Options:** call the model live every time; cache in a database; an append-only JSON-lines file per model.
- **Chosen:** one `.jsonl` file per model under `ledger/`. Each line holds the call key (prompt version and packet), the
  answer and the usage. A run reads the ledger and calls a model only when asked to record.
- **Why:** a small local model is not repeatable. The ledger makes a run reproducible and free to repeat, and a reviewer
  can read it with a text editor.
- **Drawback:** lines are not queryable, the files grow, and the key includes the prompt text, so a prompt edit
  invalidates the ledger. A database would fix that and was not worth the server for a one-user tool.
- **AI suggestion:** the AI wrote the replay code. The text-over-database choice came from the earlier storage decision (text
  for committed truth, SQLite only as a rebuilt index); a document database I suggested was rejected because it needs a server.

## 5. Sign-off: Final or Draft is decided by marks bound to file hashes

- **Options:** write the status into the run manifest; keep it only on screen; keep a separate sign-off record.
- **Chosen:** a reviewer marks each output file reviewed. The mark stores the file's sha256, so a changed file shows as
  "stale". The export is **Final** only when no input problem is open and every exported file is reviewed. Otherwise it is
  a **Draft**. The status is written to `signoff.json` inside the zip.
- **Why not the manifest:** `run_manifest.json` stays as the engine wrote it, so the byte-identical output check holds.
- **Limits:** row marks are recorded but do not decide Final.
- **A changed input resets the run:** after a review found that a re-uploaded file left old output that could still be
  signed Final, replacing an input now deletes the output and sends the run back to Scan (fixed in `420cda9`).

## 6. D06 and D07 can be acknowledged, but have no override

- **Options:** build an engine override for these two findings; record the person's answer only.
- **Chosen:** record the answer only. Passing a D06 or D07 finding closes the held journal for the review flow and is
  logged as `ASSUMED`. It moves no figure, because a held journal is not posted either way. D03, D04 and D05 are hard
  rules and cannot be overridden; D02 has a working override (decision 3).
- **Trade-off:** a reviewer who clicks Pass on D06 may expect figures to move. They do not, and the page says so.
- **What would change it:** a rule that a held journal may be posted after approval.

## 7. LangGraph for the pause, with a plain runner that gives the same bytes

- **Options:** a plain function pipeline; LangGraph with an SQLite checkpoint.
- **Chosen:** LangGraph, because a run must pause for a person and resume later. A plain runner runs the same nodes, and
  a test checks that both give identical output hashes. The run id and thread id hash the data and the three config
  files, so an approved override starts its own thread.
- **Trade-off:** more machinery for a small graph. Any config edit is a new run id.
- **Open item:** live model runs once crashed in interpreter teardown (exit 139) after the summary printed.
  `run.py` leaves with `os._exit` for `smoke` and `--live`. The root cause was not found; every ledger line is already
  written by then.
- **AI suggestion:** LangGraph with a plain-runner fallback was the AI's proposal; I took it.
