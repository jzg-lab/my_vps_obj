"""Explicit operations on one service; renewal never buys or resets traffic."""

from decimal import Decimal
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ServiceChange(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    action: Literal["pause", "resume", "renew", "reconcile_usage"]
    days: int | None = Field(default=None, gt=0, le=36500, strict=True)
    price: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")

    verified_total_bytes: int | None = Field(default=None, ge=0, le=2**53 - 1, strict=True)
    expected_raw_bytes: int | None = Field(default=None, ge=0, le=2**53 - 1, strict=True)
    evidence: str | None = Field(default=None, min_length=1, max_length=1000)

    @model_validator(mode="after")
    def validate_renewal(self) -> Self:
        values = (self.days, self.price, self.currency)
        if self.action == "renew":
            if any(value is None for value in values):
                raise ValueError("renewal_terms_required")
        elif any(value is not None for value in values):
            raise ValueError("renewal_terms_not_applicable")
        recovery = (self.verified_total_bytes, self.expected_raw_bytes, self.evidence)
        if self.action == "reconcile_usage":
            if any(value is None for value in recovery):
                raise ValueError("reconciliation_evidence_required")
        elif any(value is not None for value in recovery):
            raise ValueError("reconciliation_not_applicable")
        return self

    def request_values(self) -> dict[str, Any]:
        # Preserve existing idempotency fingerprints for pause/resume/renew requests.
        return self.model_dump(
            mode="json",
            exclude=(
                {"verified_total_bytes", "expected_raw_bytes", "evidence"}
                if self.action != "reconcile_usage"
                else set()
            ),
        )
