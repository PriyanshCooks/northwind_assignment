"""Registers the detectors, runs them and merges findings that share a key."""
from collections.abc import Callable

from app.detectors.balance import d01_trial_balance, d03_journal_balance
from app.detectors.duplicates import d14_exact_duplicates
from app.detectors.expectations import d13_expectations
from app.detectors.journals import d04_period, d05_duplicate, d06_account_exists, d07_reversal_exceeds_balance
from app.detectors.mapping import d02_mapping
from app.detectors.rates import d08_required_rates
from app.detectors.reconciliation import d09_subledger, d10_cross_file_ties, d11_intercompany_pairing
from app.detectors.text_scan import d12_instruction_wording
from app.domain.findings import Finding
from app.domain.runs import Context

Detector = Callable[[Context], list[Finding]]

DETECTORS: tuple[Detector, ...] = (
    d01_trial_balance, d02_mapping, d03_journal_balance, d04_period, d05_duplicate, d06_account_exists,
    d07_reversal_exceeds_balance, d08_required_rates, d09_subledger, d10_cross_file_ties,
    d11_intercompany_pairing, d12_instruction_wording, d13_expectations, d14_exact_duplicates,
)


def run_all(ctx: Context) -> list[Finding]:
    """Every detector runs; two findings with one key become one. Order is stable: code, file, line."""
    merged: dict[str, Finding] = {}
    for detector in DETECTORS:
        for finding in detector(ctx):
            merged[finding.key] = merged[finding.key].merged_with(finding) if finding.key in merged else finding
    return sorted(merged.values(), key=lambda f: (f.code, f.file, f.line or 0, f.key))
