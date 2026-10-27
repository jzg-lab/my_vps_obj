"""Contracts for local labels attached to managed node UUIDs."""

from datetime import datetime

from pydantic import ConfigDict, Field, field_validator

from bot.app.web.http_contracts import HttpBodyModel, HttpResponseModel


class ConsoleNodeMetadataBody(HttpBodyModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    display_name: str | None = Field(default=None, max_length=120)
    region: str | None = Field(default=None, max_length=120)
    provider: str | None = Field(default=None, max_length=120)

    @field_validator("display_name", "region", "provider")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError("invalid_node_metadata_text")
        value = value.strip()
        return value or None


class ConsoleNodeMetadataOut(HttpResponseModel):
    node_id: str
    display_name: str | None
    region: str | None
    provider: str | None
    updated_at: datetime


class ConsoleNodeMetadataDeletedOut(HttpResponseModel):
    node_id: str
    deleted: bool
