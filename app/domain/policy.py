"""Policy values (from config/policy.toml) and the assumptions registry (config/assumptions.toml)."""
from datetime import date

from app.domain.refs import Model


class PolicyMeta(Model):
    source: str
    source_sha256: str
    status: str


class Period(Model):
    start: date
    end: date


class Account(Model):
    difference_account: str


class Intercompany(Model):
    residual_account: str


class Rounding(Model):
    report_decimal_places: int


class Policy(Model):
    meta: PolicyMeta
    period: Period
    translation: Account
    foreign_currency_items: Account
    intercompany: Intercompany
    rounding: Rounding


class Override(Model):
    """A human decision on a finding (config/overrides.toml). `open` means the reviewer has not signed it off yet.

    `evidence_hash` fingerprints the rows the reviewer looked at; if they change, the decision is stale.
    """

    target: str
    decision: str
    to: str
    approver: str
    reason: str
    status: str
    effect_if_reversed: str
    evidence_hash: str


class Assumption(Model):
    id: str
    key: str
    value: bool | str
    basis: str
    status: str
    alternative: str
