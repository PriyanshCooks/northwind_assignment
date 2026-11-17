"""Settings: config/policy.toml and config/assumptions.toml. The engine reads policy values only from these files."""
import tomllib
from pathlib import Path

from app.domain.policy import Assumption, Policy
from app.utils.paths import CONFIG_DIR


def load_policy(path: Path = CONFIG_DIR / "policy.toml") -> Policy:
    return Policy.model_validate(tomllib.loads(path.read_text(encoding="utf-8")))


def load_assumption_rows(path: Path = CONFIG_DIR / "assumptions.toml") -> list[Assumption]:
    document = tomllib.loads(path.read_text(encoding="utf-8"))
    return [Assumption.model_validate(row) for row in document["assumption"]]


def load_assumptions(path: Path = CONFIG_DIR / "assumptions.toml") -> dict[str, bool | str]:
    """Assumption switches by key, for example {'je017': 'reject', 'journals_in_tb': False}."""
    return {row.key: row.value for row in load_assumption_rows(path)}
