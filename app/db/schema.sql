-- Evidence store. Disposable: rebuilt from the input files, config and the committed ledger on every run.
-- Every JSON column is checked with json_valid, so a malformed document cannot be stored.

CREATE TABLE IF NOT EXISTS runs (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL UNIQUE,
    input_hash TEXT NOT NULL,
    manifest TEXT NOT NULL CHECK (json_valid(manifest))
);

CREATE TABLE IF NOT EXISTS findings (
    run_id TEXT NOT NULL,
    key TEXT NOT NULL,
    code TEXT NOT NULL,
    severity TEXT NOT NULL,
    body TEXT NOT NULL CHECK (json_valid(body)),
    PRIMARY KEY (run_id, key)
);

CREATE TABLE IF NOT EXISTS facts (
    key TEXT PRIMARY KEY,
    evidence_sha256 TEXT NOT NULL,
    body TEXT NOT NULL CHECK (json_valid(body))
);

CREATE TABLE IF NOT EXISTS llm_ledger (
    key TEXT PRIMARY KEY,
    model TEXT NOT NULL,
    body TEXT NOT NULL CHECK (json_valid(body))
);

CREATE TABLE IF NOT EXISTS origin_rows (
    run_id TEXT NOT NULL,
    account TEXT NOT NULL,
    seq INTEGER NOT NULL,
    body TEXT NOT NULL CHECK (json_valid(body)),
    PRIMARY KEY (run_id, account, seq)
);

CREATE INDEX IF NOT EXISTS origin_rows_by_account ON origin_rows (run_id, account);

CREATE TABLE IF NOT EXISTS traces (
    run_id TEXT NOT NULL,
    figure TEXT NOT NULL,
    body TEXT NOT NULL CHECK (json_valid(body)),
    PRIMARY KEY (run_id, figure)
);
