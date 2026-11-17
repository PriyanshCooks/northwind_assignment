"""run_manifest.json: what went in, which code and policy ran, and a hash of every other output file."""
from pathlib import Path

from app.utils.hashing import dumps, sha256_file, sha256_text
from app.utils.paths import CONFIG_DIR, ROOT
from app.writers.statements import write_text


def code_hash() -> str:
    """Hash of the application source with line endings normalised, so a checkout on any system agrees."""
    parts = []
    for path in sorted((ROOT / "app").rglob("*")):
        if path.is_file() and path.suffix in {".py", ".sql"} and "__pycache__" not in path.parts:
            text = path.read_bytes().decode("utf-8").replace("\r\n", "\n")
            parts.append(f"{path.relative_to(ROOT).as_posix()}\n{text}")
    return sha256_text("\n".join(parts))


def write_manifest(data_dir: Path, out: Path, outputs: list[str], config_dir: Path = CONFIG_DIR) -> None:
    body = {
        "input_hashes": {p.name: sha256_file(p) for p in sorted(data_dir.iterdir()) if p.is_file()},
        "policy_sha256": sha256_file(config_dir / "policy.toml"),
        "assumptions_sha256": sha256_file(config_dir / "assumptions.toml"),
        "overrides_sha256": sha256_file(config_dir / "overrides.toml"),
        "code_sha256": code_hash(),
        "ledger_sha256": None,
        "output_hashes": {name: sha256_file(out / name) for name in sorted(outputs)},
    }
    write_text(out / "run_manifest.json", dumps(body))
