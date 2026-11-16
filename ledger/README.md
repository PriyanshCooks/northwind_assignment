# Ledger

Recorded AI calls, **one file per model**, for example `qwen3-4b-dev.jsonl`. Append-only, one JSON object per line.

Key = SHA-256 of (packet, prompt version, model, settings, schema). A default run replays this file and never calls a
provider; a missing entry falls back to the rule-based proposer. `python run.py consolidate --live` appends new
entries. Text quoted from the data (including the JE-006 memo) lives here as untrusted evidence and is never
promoted to a trusted fact.
