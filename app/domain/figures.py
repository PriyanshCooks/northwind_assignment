"""A control figure is Determined, Provisional or Unknown. A null with a reason is a type, not a convention."""
from typing import Annotated, Literal

from pydantic import Field, TypeAdapter

from app.domain.refs import Model, Money


class Determined(Model):
    kind: Literal["determined"] = "determined"
    value: Money | dict[str, int]


class Provisional(Model):
    kind: Literal["provisional"] = "provisional"
    value: Money | dict[str, int]
    open_items: tuple[str, ...]


class Unknown(Model):
    kind: Literal["unknown"] = "unknown"
    reason: str


Figure = Annotated[Determined | Provisional | Unknown, Field(discriminator="kind")]
figure_adapter: TypeAdapter[Determined | Provisional | Unknown] = TypeAdapter(Figure)
