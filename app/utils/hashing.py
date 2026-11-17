"""SHA-256 of bytes, text, files and canonical JSON. One JSON writer, so outputs and hashes agree."""
import hashlib
import json
import re
from decimal import Decimal
from pathlib import Path
from typing import Any

_DECIMAL_TOKEN = "__decimal__"
_BARE_NUMBER = re.compile(r'"' + _DECIMAL_TOKEN + r'(-?[0-9.]+)"')


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def _prepare(value: Any) -> Any:
    if isinstance(value, Decimal):
        return _DECIMAL_TOKEN + format(value, "f")
    if isinstance(value, dict):
        return {str(k): _prepare(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_prepare(v) for v in value]
    return value


def dumps(value: Any, indent: int | None = 2, sort_keys: bool = False) -> str:
    """JSON text with Decimal written as a bare number (never through float) and no trailing newline."""
    separators = (",", ":") if indent is None else None
    text = json.dumps(_prepare(value), indent=indent, sort_keys=sort_keys, separators=separators, ensure_ascii=False)
    return _BARE_NUMBER.sub(r"\1", text)


def json_hash(value: Any) -> str:
    return sha256_text(dumps(value, indent=None, sort_keys=True))
