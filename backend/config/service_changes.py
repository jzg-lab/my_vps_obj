"""Explicit operations on one service; renewal never buys or resets traffic."""

from decimal import Decimal
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ServiceChange(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    action: Literal["pause", "resume", "renew"]
    days: int | None = Field(default=None, gt=0, le=36500, strict=True)
    price: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")

    @model_validator(mode="after")
    def validate_renewal(self) -> Self:
        values = (self.days, self.price, self.currency)
        if self.action == "renew":
            if any(value is None for value in values):
                raise ValueError("renewal_terms_required")
        elif any(value is not None for value in values):
            raise ValueError("renewal_terms_not_applicable")
        return self
