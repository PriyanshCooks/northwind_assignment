"""Everything a reasoning checkpoint may look at, as plain text and numbers, built once from a finished run.
No engine object leaks through: a model sees this and nothing else."""
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path


@dataclass(frozen=True)
class Evidence:
    data_dir: Path
    files: frozenset[str]  # the names of the run's input files: the only files a tool may open
    last_year: int = 2024  # the last year of the reporting period; a later date in a data line is not plausible
    rules: dict[str, str] = field(default_factory=dict)  # clause name -> text
    calculations: dict[str, str] = field(default_factory=dict)  # calc id -> record as text
    lineage: dict[str, str] = field(default_factory=dict)  # row id -> its source lines as text
    related: dict[str, str] = field(default_factory=dict)  # group account -> mapped local accounts as text
    results: dict[str, Decimal] = field(default_factory=dict)  # calc id -> its result
    # flag or concern -> the file:line or calc ids the rules already confirm
    confirmed: dict[str, frozenset[str]] = field(default_factory=dict)

    def lines(self, file: str) -> list[str]:
        return (self.data_dir / file).read_text(encoding="utf-8").splitlines()
    # file:line of an fx_rates row -> percent from the median of its pair's other rates (the D15 measure)
    rate_gaps: dict[str, Decimal] = field(default_factory=dict)
    rate_tolerance: Decimal = Decimal(10)  # A14
    # file:line of a map row whose name reads as one nature and whose group account has that same nature
    nature_agrees: frozenset[str] = frozenset()
