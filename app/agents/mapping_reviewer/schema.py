"""Pydantic output model only. The allowed replacement accounts are generated from the chart of accounts."""
from functools import cache
from typing import ClassVar, Literal

from pydantic import create_model

from app.agents.review.verdict import Verdict


class MappingVerdictBase(Verdict):
    CATEGORIES: ClassVar[tuple[str, ...]] = ("name_mismatch", "wrong_statement_type", "sign_unusual")
    name_mismatch: bool
    wrong_statement_type: bool
    sign_unusual: bool


@cache
def mapping_verdict_model(codes: tuple[str, ...]) -> type[MappingVerdictBase]:
    """The same verdict with `better_group_code` limited to real group accounts, or "none"."""
    allowed = Literal[("none", *codes)]  # type: ignore[valid-type]
    return create_model("MappingVerdict", __base__=MappingVerdictBase, better_group_code=(allowed, "none"))
