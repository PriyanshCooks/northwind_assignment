"""The .env file and secret scrubbing. A key is read from the environment only; it is never written to a ledger, a
log or an error message."""
import os
import re
from pathlib import Path

from app.utils.paths import ROOT

KEY_VARIABLES = ("OPENAI_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY")
SECRET_PATTERN = re.compile(r"sk-[A-Za-z0-9_\-]{8,}|Bearer\s+[A-Za-z0-9._\-]{8,}", re.IGNORECASE)


def load_env(path: Path = ROOT / ".env") -> None:
    """Copy KEY=value lines into the environment. A variable already set, or empty in the file, is left alone."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        name, sep, value = line.partition("=")
        name, value = name.strip(), value.strip().strip("\"'")
        if sep and name and not name.startswith("#") and value:
            os.environ.setdefault(name, value)


def scrub(text: str) -> str:
    """Hide anything shaped like an API key or bearer token, and the exact value of any key held in the environment."""
    for name in KEY_VARIABLES:
        value = os.environ.get(name, "")
        if len(value) >= 8:
            text = text.replace(value, "[hidden]")
    return SECRET_PATTERN.sub("[hidden]", text)
