"""Optional native-request receipt; copied only inside the owned TLS container."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

import aiohttp
from aiohttp import web

OBSERVATIONS = Path("/tmp/subscription-client/observations")
LIMIT = 2 * 1024 * 1024


def empty_subscription(body: bytes, content_type: str) -> bool:
    if "html" in content_type.lower():
        return False
    stripped = body.strip(b" \t\r\n")
    if not stripped:
        return True
    try:
        return not base64.b64decode(b"".join(stripped.split()), validate=True).strip(b" \t\r\n")
    except (ValueError, binascii.Error):
        return False


def record_response(
    directory: Path, request: web.Request, body: bytes, response: aiohttp.ClientResponse
) -> None:
    path = directory / "request.json"
    if path.is_symlink() or path.stat().st_size > 8192:
        raise ValueError("native_observation_request_file")
    registration = json.loads(path.read_bytes())
    marker = registration.get("native_observation")
    if marker is None:
        return
    if not isinstance(marker, str) or UUID(marker).hex != marker:
        raise ValueError("native_observation_marker")
    url = registration.get("url")
    if not isinstance(url, str):
        raise ValueError("native_observation_url")
    parts = urlsplit(url)
    target = parts.path + ("?" + parts.query if parts.query else "")
    if (
        parts.scheme != "https"
        or parts.netloc != "127.0.0.1:3010"
        or request.host != parts.netloc
        or request.raw_path != target
        or len(body) > LIMIT
        or not OBSERVATIONS.is_dir()
        or OBSERVATIONS.is_symlink()
        or OBSERVATIONS.stat().st_mode & 0o077
    ):
        raise ValueError("native_observation_scope")
    receipt = {
        "attempt": marker,
        "url_sha256": hashlib.sha256(url.encode()).hexdigest(),
        "upstream_status": response.status,
        "body_bytes": len(body),
        "body_sha256": hashlib.sha256(body).hexdigest(),
        "empty_subscription": empty_subscription(body, response.headers.get("Content-Type", "")),
    }
    fd = os.open(
        OBSERVATIONS / (marker + ".json"),
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        0o600,
    )
    with os.fdopen(fd, "w") as stream:
        json.dump(receipt, stream)
