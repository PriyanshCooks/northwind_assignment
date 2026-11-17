"""The supplied data is exactly what was recorded in config/bundle_manifest.sha256."""
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "Northwind_TakeHome_v2" / "data"
MANIFEST = ROOT / "config" / "bundle_manifest.sha256"


def recorded() -> dict[str, str]:
    lines = MANIFEST.read_text(encoding="utf-8").splitlines()
    return {name: digest for digest, name in (line.split("  ", 1) for line in lines if line)}


def actual() -> dict[str, str]:
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(DATA.iterdir()) if p.is_file()}


def test_manifest_lists_all_fifteen_data_files() -> None:
    assert len(recorded()) == 15
    assert set(recorded()) == set(actual())


def test_every_data_file_matches_its_recorded_hash() -> None:
    expected, found = recorded(), actual()
    differing = sorted(name for name in expected if found.get(name) != expected[name])
    assert differing == []
