"""Everything a reasoning checkpoint may look at, as plain text and numbers, built once from a finished run.
No engine object leaks through: a model sees this and nothing else."""
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Evidence:
    data_dir: Path
    files: frozenset[str]  # the names of the run's input files: the only files a tool may open
    rules: dict[str, str] = field(default_factory=dict)  # clause name -> text
    calculations: dict[str, str] = field(default_factory=dict)  # calc id -> record as text
    lineage: dict[str, str] = field(default_factory=dict)  # row id -> its source lines as text
    related: dict[str, str] = field(default_factory=dict)  # group account -> mapped local accounts as text
