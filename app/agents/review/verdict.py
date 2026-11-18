"""What a reviewer may say: one boolean per risk category, never a list, and `risk` worked out in code.

A small model given a list field can contradict itself (risk false while naming a category) or loop. Booleans cannot."""
from typing import ClassVar

from pydantic import BaseModel


class Verdict(BaseModel):
    CATEGORIES: ClassVar[tuple[str, ...]] = ()
    reason: str

    @property
    def flags(self) -> tuple[str, ...]:
        return tuple(name for name in self.CATEGORIES if getattr(self, name))

    @property
    def risk(self) -> bool:
        return bool(self.flags)
