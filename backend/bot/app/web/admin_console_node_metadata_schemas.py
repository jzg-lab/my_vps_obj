"""Contracts for local labels attached to managed node UUIDs."""

from datetime import datetime
from ipaddress import ip_address

from pydantic import ConfigDict, Field, field_validator

from bot.app.web.http_contracts import HttpBodyModel, HttpResponseModel
from config.country_codes import COUNTRY_CODES


class ConsoleNodeMetadataBody(HttpBodyModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    display_name: str | None = Field(default=None, max_length=120)
    region: str | None = Field(default=None, max_length=120)
    provider: str | None = Field(default=None, max_length=120)
    country_code: str | None = Field(default=None, max_length=2)
    country_lookup_ip: str | None = Field(default=None, max_length=45)

    @field_validator("country_lookup_ip")
    @classmethod
    def normalize_lookup_ip(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        ip = ip_address(value.strip())
        if not ip.is_global or ip.is_multicast or "%" in str(ip):
            raise ValueError("invalid_node_country_lookup_ip")
        return str(ip)

    @field_validator("country_code")
    @classmethod
    def normalize_country(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        code = value.strip().upper()
        if code not in COUNTRY_CODES:
            raise ValueError("invalid_node_country")
        return code

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
    country_code: str | None = None
    country_lookup_ip: str | None = None
    updated_at: datetime


class ConsoleNodeMetadataDeletedOut(HttpResponseModel):
    node_id: str
    deleted: bool
