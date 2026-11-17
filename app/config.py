"""Settings: config/policy.toml and config/assumptions.toml. The engine reads policy values only from these files."""
import tomllib
from pathlib import Path

from app.domain.policy import Assumption, Override, Policy
from app.utils.paths import CONFIG_DIR


def load_policy(path: Path = CONFIG_DIR / "policy.toml") -> Policy:
    return Policy.model_validate(tomllib.loads(path.read_text(encoding="utf-8")))


def load_assumption_rows(path: Path = CONFIG_DIR / "assumptions.toml") -> list[Assumption]:
    document = tomllib.loads(path.read_text(encoding="utf-8"))
    return [Assumption.model_validate(row) for row in document["assumption"]]


def load_assumptions(path: Path = CONFIG_DIR / "assumptions.toml") -> dict[str, bool | str]:
    """Assumption switches by key, for example {'je017': 'reject', 'journals_in_tb': False}."""
    return {row.key: row.value for row in load_assumption_rows(path)}


def load_overrides(path: Path = CONFIG_DIR / "overrides.toml") -> list[Override]:
    document = tomllib.loads(path.read_text(encoding="utf-8"))
    return [Override.model_validate(row) for row in document.get("override", [])]


def override_switches(rows: list[Override]) -> dict[str, bool | str]:
    """A mapping override sets the switch that apply_mapping reads: 'mapping:UK:2310' becomes map_uk_2310."""
    switches: dict[str, bool | str] = {}
    for row in rows:
        kind, entity, code = row.target.split(":")
        if kind == "mapping" and row.decision == "remap":
            switches[f"map_{entity.lower()}_{code}"] = f"remap_{row.to}"
    return switches
