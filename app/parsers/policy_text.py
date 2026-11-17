"""Binds config/policy.toml to group_policies.md by hash: change the text without re-approval and the run blocks."""
from pathlib import Path

from app.domain.policy import Policy
from app.utils.hashing import sha256_file


class PolicyBlocked(Exception):
    """group_policies.md no longer matches the text policy.toml was approved against."""


def check_binding(policy: Policy, data_dir: Path) -> None:
    """Policy-dependent steps cannot run on a policy nobody approved. Re-approve by updating source_sha256."""
    source = data_dir / Path(policy.meta.source).name
    actual = sha256_file(source)
    if actual != policy.meta.source_sha256:
        raise PolicyBlocked(
            f"{source.name} has changed since config/policy.toml was approved (hash {actual[:12]}, approved "
            f"{policy.meta.source_sha256[:12]}): re-read the policy and approve it again before the run continues"
        )
