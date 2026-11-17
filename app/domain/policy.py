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


class Assumption(Model):
    id: str
    key: str
    value: bool | str
    basis: str
    status: str
    alternative: str
