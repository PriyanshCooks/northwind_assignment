"""What a reasoning checkpoint may say. Every field is text or a menu choice: there is no number field and no field
that can name a disposition, so a model's output cannot become a figure or a decision."""
from typing import Literal

from pydantic import BaseModel, Field

InputFlag = Literal[
    "no_valid_name", "value_not_plausible", "label_contradicts_meaning", "near_miss_of_expected",
    "inconsistent_with_neighbours", "nature_mismatch", "unit_or_direction_suspect",
]
CalcConcern = Literal[
    "sign_implausible", "magnitude_implausible", "formula_does_not_fit_nature", "inconsistent_with_related",
]


class LineClaim(BaseModel):
    cite: str = Field(description="the line, as file:line")
    flag: InputFlag
    reason: str = Field(max_length=300, description="one short sentence")
    quoted: list[str] = Field(default_factory=list, max_length=6, description="exact pieces of the cited line")


class InputReading(BaseModel):
    claims: list[LineClaim] = Field(default_factory=list, max_length=30)


class CalcClaim(BaseModel):
    cite: str = Field(description="the calculation id, for example fig:total_assets")
    concern: CalcConcern
    reason: str = Field(max_length=300, description="one short sentence")
    quoted: list[str] = Field(default_factory=list, max_length=6, description="exact pieces of the record")


class CalcReview(BaseModel):
    claims: list[CalcClaim] = Field(default_factory=list, max_length=12)


class TraceStepClaim(BaseModel):
    cite: str = Field(description="a source file:line or a calculation id")
    note: str = Field(max_length=300, description="what this step shows")
    quoted: list[str] = Field(default_factory=list, max_length=6)


class Investigation(BaseModel):
    """The chain from an output row back to the source lines. It reports; it never proposes a corrected value."""

    chain: list[TraceStepClaim] = Field(default_factory=list, max_length=8)
    cause: str = Field(max_length=300, default="", description="which input looks wrong and what else it feeds")
