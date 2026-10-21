"""Commercial terms shared by plan templates, activation snapshots and services."""

from decimal import Decimal
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ServicePlanTerms(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=2000)
    resource_type: Literal["shared", "dedicated"]
    traffic_rule: Literal["total", "monthly"]
    quota_bytes: int = Field(gt=0, le=2**53 - 1, strict=True)
    validity_days: int = Field(gt=0, le=36500, strict=True)
    price: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    squad_uuids: list[UUID] = Field(default_factory=list, max_length=100)
    resource_pool: str | None = Field(default=None, min_length=1, max_length=120)

    @model_validator(mode="after")
    def validate_resources(self) -> Self:
        if len(set(self.squad_uuids)) != len(self.squad_uuids):
            raise ValueError("duplicate_squad")
        if self.resource_type == "shared":
            if not self.squad_uuids or self.resource_pool is not None:
                raise ValueError("shared_plan_requires_squads_only")
        elif self.squad_uuids or not self.resource_pool:
            raise ValueError("dedicated_plan_requires_resource_pool_only")
        return self
