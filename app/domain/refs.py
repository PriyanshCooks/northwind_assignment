"""The unit of traceability (a source row) and the base types shared by every domain model."""
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, PlainSerializer

from app.utils.hashing import sha256_text
from app.utils.money import to_decimal

# Decimal in, Decimal out in Python; a string in JSON, so no precision is lost on the way to a file or database.
Money = Annotated[Decimal, BeforeValidator(to_decimal), PlainSerializer(lambda v: str(v), return_type=str)]


class Model(BaseModel):
    model_config = ConfigDict(frozen=True)


class SourceRef(Model):
    """One row of one input file: where a number came from."""

    file: str
    line: int
    row_hash: str

    def __str__(self) -> str:
        return f"{self.file}:{self.line}"


def make_ref(file: str, line: int, raw_text: str) -> SourceRef:
    return SourceRef(file=file, line=line, row_hash=sha256_text(raw_text))
