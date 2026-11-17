"""Repository paths in one place. The input data folder is a command-line option; this is only its default."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"
DEFAULT_DATA_DIR = ROOT / "Northwind_TakeHome_v2" / "data"
DEFAULT_OUTPUT_DIR = ROOT / "output"
RUNTIME_DIR = ROOT / ".northwind"
