"""Request and response shapes for the review UI. Plain data: no figure is computed here."""
import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.services.upload_service import EXPECTED_FILES

PATCH = re.compile(r"^(?P<file>[^:]+):\d+\.\w+=")
APPEND = re.compile(r"^(?P<file>[^=]+)=")


class NewRun(BaseModel):
    name: str = Field(default="", max_length=60)
    use_sample: bool = False


class Decisions(BaseModel):
    approver: str = Field(min_length=1, max_length=60)
    decisions: dict[str, str]

    @field_validator("decisions")
    @classmethod
    def only_approve_or_reject(cls, value: dict[str, str]) -> dict[str, str]:
        bad = sorted(t for t, choice in value.items() if choice not in {"approve", "reject"})
        if bad:
            raise ValueError(f"decision must be approve or reject: {bad}")
        return value


class Outputs(BaseModel):
    files: list[str]


class WhatIf(BaseModel):
    """Patches look like file:LINE.column=value, appends like file=csv row. The file must be one of the 15."""

    name: str = Field(default="", max_length=60)
    patches: list[str] = Field(default_factory=list, max_length=20)
    appends: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("patches", "appends")
    @classmethod
    def known_file(cls, value: list[str], info: object) -> list[str]:
        pattern = PATCH if getattr(info, "field_name", "") == "patches" else APPEND
        for text in value:
            match = pattern.match(text)
            if not match or match["file"] not in EXPECTED_FILES:
                raise ValueError(f"{text!r}: expected a change to one of the 15 supplied files")
        return value


class RowDecision(BaseModel):
    """One reviewer decision on one finding: pass (acknowledge) or override (only where the rules allow it)."""

    key: str = Field(min_length=1, max_length=200)
    action: Literal["pass", "override"]
    reviewer: str = Field(min_length=1, max_length=60)
    note: str = Field(default="", max_length=500)
