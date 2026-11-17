"""The environment check behind `run.py check`: Python, the data bundle, and the policy binding."""
import sys
import tomllib
from pathlib import Path

from app.config import load_assumptions, load_policy
from app.parsers.policy_text import PolicyBlocked, check_binding, compare, read_policy
from app.utils.hashing import sha256_file
from app.utils.paths import CONFIG_DIR


def _manifest(path: Path) -> dict[str, str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return {name.strip(): digest for digest, name in (line.split("  ", 1) for line in lines if line)}


def check_environment(data_dir: Path, config_dir: Path = CONFIG_DIR) -> list[tuple[str, bool, str]]:
    results = [("python 3.11 or newer", sys.version_info >= (3, 11), sys.version.split()[0])]
    recorded = _manifest(config_dir / "bundle_manifest.sha256")
    bad = [n for n, digest in recorded.items() if not (data_dir / n).is_file() or sha256_file(data_dir / n) != digest]
    results.append(("supplied data matches config/bundle_manifest.sha256", not bad, ", ".join(bad) or "bundle intact"))
    policy = load_policy(config_dir / "policy.toml")
    try:
        check_binding(policy, data_dir)
        results.append(("policy.toml is bound to group_policies.md", True, policy.meta.status))
    except PolicyBlocked as stop:
        results.append(("policy.toml is bound to group_policies.md", False, str(stop)))
    approved = tomllib.loads((config_dir / "policy.toml").read_text(encoding="utf-8"))
    problems = compare(read_policy((data_dir / Path(policy.meta.source).name).read_text(encoding="utf-8")), approved)
    results.append(("the policy text, read by the lexicon, agrees with policy.toml", not problems,
                    "; ".join(f"{f}: {why}" for f, why in problems)))
    results.append(("assumptions load", bool(load_assumptions(config_dir / "assumptions.toml")), ""))
    return results
