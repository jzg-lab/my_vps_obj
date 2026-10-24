"""Contracts for manual records, not execution-layer node onboarding."""

import re
from datetime import datetime
from ipaddress import ip_address
from typing import Literal

from pydantic import ConfigDict, Field, field_validator

from bot.app.web.http_contracts import HttpBodyModel, HttpResponseModel
from db.node_asset_models import NodeAsset


class ConsoleNodeAssetBody(HttpBodyModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=120)
    address: str = Field(min_length=1, max_length=253)
    notes: str = Field(default="", max_length=2000)

    @field_validator("name", "address", "notes")
    @classmethod
    def no_control_characters(cls, value: str) -> str:
        if any((ord(char) < 32 and char not in "\n\t") or ord(char) == 127 for char in value):
            raise ValueError("invalid_node_asset_text")
        return value

    @field_validator("name")
    @classmethod
    def single_line_name(cls, value: str) -> str:
        if "\n" in value or "\t" in value:
            raise ValueError("invalid_node_asset_name")
        return value

    @field_validator("address")
    @classmethod
    def host_only(cls, value: str) -> str:
        # Syntax only: private addresses are valid inventory, never connection targets.
        if "%" in value:
            raise ValueError("invalid_node_asset_address")
        try:
            ip_address(value)
        except ValueError:
            host = value.removesuffix(".")
            labels = host.split(".")
            if all(label.isdigit() for label in labels) or any(
                not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label)
                for label in labels
            ):
                raise ValueError("invalid_node_asset_address") from None
        return value


class ConsoleNodeAssetsQuery(HttpBodyModel):
    model_config = ConfigDict(extra="forbid")

    page: int = Field(default=0, ge=0, le=1_000_000)
    page_size: int = Field(default=20, ge=1, le=100)


class ConsoleNodeAssetOut(HttpResponseModel):
    id: str
    name: str
    address: str
    notes: str
    management_state: Literal["unmanaged"]
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_orm_asset(cls, row: NodeAsset) -> "ConsoleNodeAssetOut":
        return cls(
            id=row.id,
            name=row.name,
            address=row.address,
            notes=row.notes,
            management_state="unmanaged",
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


class ConsoleNodeAssetsListOut(HttpResponseModel):
    items: list[ConsoleNodeAssetOut]
    total: int
    page: int
    page_size: int


class ConsoleNodeAssetDeletedOut(HttpResponseModel):
    id: str
    deleted: Literal[True]
