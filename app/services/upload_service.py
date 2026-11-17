"""Uploaded files are data. Only the 15 expected names are accepted, each is size-limited, and each is read by the
same parser the consolidation uses, so a contract error here is the error the run would hit later."""
import tempfile
from collections.abc import Callable
from pathlib import Path

from app.parsers.acquisition_note import load_acquisition
from app.parsers.contracts import ContractError
from app.parsers.entities import load_entities, load_intercompany, load_prior_equity, load_subledger
from app.parsers.fx_rates import load_rates
from app.parsers.journals import load_journals
from app.parsers.mappings import load_coa, load_map
from app.parsers.policy_text import read_policy
from app.parsers.tb_adapters import load_india_monthly, load_tb

MAX_BYTES = 1_000_000


def _policy(path: Path) -> None:
    if not read_policy(path.read_text(encoding="utf-8")):
        raise ContractError(path.name, 1, "no policy clause found")


CHECKS: dict[str, Callable[[Path], object]] = {
    "entities.csv": load_entities,
    "tb_us.csv": lambda p: load_tb(p, "US", "USD"),
    "tb_uk.csv": lambda p: load_tb(p, "UK", "GBP"),
    "tb_in.csv": lambda p: load_tb(p, "IN", "INR"),
    "map_uk.csv": lambda p: load_map(p, "UK"),
    "map_in.csv": lambda p: load_map(p, "IN"),
    "group_coa.csv": load_coa,
    "fx_rates.csv": load_rates,
    "adjustments.json": load_journals,
    "intercompany.csv": load_intercompany,
    "subledger_controls.csv": load_subledger,
    "prior_year_group.csv": load_prior_equity,
    "acquisition_note.md": load_acquisition,
    "in_pl_monthly.csv": load_india_monthly,
    "group_policies.md": _policy,
}
EXPECTED_FILES = frozenset(CHECKS)


def validate(path: Path) -> str | None:
    """None when the file meets its contract, else the one-line reason. Never raises on bad content."""
    try:
        CHECKS[path.name](path)
    except ContractError as error:
        return str(error)
    except (ValueError, KeyError, IndexError, UnicodeError, OSError) as error:
        return f"{path.name}: cannot be read ({type(error).__name__})"
    return None


def validate_bytes(name: str, body: bytes) -> str | None:
    """Check content before it is stored, in a scratch file named like the real one."""
    with tempfile.TemporaryDirectory(prefix="northwind_upload_") as tmp:
        scratch = Path(tmp) / name
        scratch.write_bytes(body)
        return validate(scratch)


def file_status(data_dir: Path) -> list[dict[str, object]]:
    """One row per expected file: present or missing, and the contract error if it has one."""
    rows: list[dict[str, object]] = []
    for name in sorted(EXPECTED_FILES):
        path = data_dir / name
        present = path.is_file()
        rows.append({"name": name, "present": present, "bytes": path.stat().st_size if present else 0,
                     "error": validate(path) if present else None})
    return rows
