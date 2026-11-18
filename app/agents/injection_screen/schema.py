"""Pydantic output model only: one boolean."""
from typing import ClassVar

from app.agents.review.verdict import Verdict


class InjectionVerdict(Verdict):
    CATEGORIES: ClassVar[tuple[str, ...]] = ("addressed_to_reviewer",)
    addressed_to_reviewer: bool
