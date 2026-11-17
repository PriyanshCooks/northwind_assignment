"""Answer a call from the ledger alone."""
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from app.llm.ledger import Ledger, LedgerMiss, RecordedFailure

T = TypeVar("T", bound=BaseModel)


def replay(ledger: Ledger, key: str, schema: type[T]) -> T:
    entry: dict[str, Any] | None = ledger.get(key)
    if entry is None:
        raise LedgerMiss(f"no recorded answer for call {key[:12]} in {ledger.path.name}")
    if not entry["validated"]:
        raise RecordedFailure(f"the recorded call {key[:12]} failed: {entry.get('error')}")
    try:
        return schema.model_validate(entry["response"])
    except ValidationError as error:
        reason = f"{error.error_count()} errors"
        raise RecordedFailure(f"recorded answer {key[:12]} no longer fits the schema ({reason})") from error
