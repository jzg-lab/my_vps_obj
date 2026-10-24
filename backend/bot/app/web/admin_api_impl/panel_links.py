"""Browser-safe links from Mini Shop admin to Remnawave Panel."""

import re
from ipaddress import IPv6Address, ip_address
from urllib.parse import SplitResult, urlsplit, urlunsplit

from bot.services.panel_api_compat import numeric_panel_user_id


def _panel_browser_base(raw_url: str) -> SplitResult | None:
    try:
        parsed = urlsplit(raw_url)
        hostname = parsed.hostname
        _ = parsed.port
    except ValueError:
        return None

    scheme = parsed.scheme.lower()
    if (
        scheme not in {"http", "https"}
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        return None

    base_path = parsed.path.rstrip("/")
    if base_path.lower().endswith("/api"):
        base_path = base_path[:-4].rstrip("/")
    return parsed._replace(scheme=scheme, path=base_path, query="", fragment="")


def build_panel_maintenance_url(panel_public_url: object) -> str | None:
    """Use explicit public configuration only; never resolve DNS or contact Panel."""
    if not isinstance(panel_public_url, str):
        return None
    raw_url = panel_public_url.strip()
    if (
        not raw_url
        or "\\" in raw_url
        or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in raw_url)
    ):
        return None
    parsed = _panel_browser_base(raw_url)
    if parsed is None or parsed.hostname is None:
        return None
    hostname = parsed.hostname.lower().rstrip(".")
    if not hostname.isascii() or "%" in parsed.netloc or parsed.port == 0:
        return None
    try:
        address = ip_address(hostname)
    except ValueError:
        labels = hostname.split(".")
        if (
            len(labels) < 2
            or len(hostname) > 253
            or any(
                re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", part) is None
                for part in labels
            )
            or re.fullmatch(r"[a-z]{2,63}|xn--[a-z0-9-]+", labels[-1]) is None
            or labels[-1]
            in {
                "localhost",
                "local",
                "localdomain",
                "internal",
                "lan",
                "home",
                "corp",
                "intranet",
                "private",
                "test",
                "invalid",
                "example",
                "onion",
                "arpa",
            }
        ):
            return None
        authority = hostname
    else:
        if not address.is_global or address.is_multicast or address.is_reserved:
            return None
        if isinstance(address, IPv6Address) and (
            address.ipv4_mapped is not None
            or address.sixtofour is not None
            or address.teredo is not None
        ):
            return None
        authority = f"[{address}]" if isinstance(address, IPv6Address) else str(address)
    if parsed.port is not None:
        authority += f":{parsed.port}"
    return urlunsplit(parsed._replace(netloc=authority))


def build_panel_user_admin_url(
    panel_api_url: object,
    panel_user_reference: object,
    panel_public_url: object = None,
) -> str | None:
    """Build the Remnawave 3.x user-card URL when a numeric user id is known.

    Remnawave 2.x stores UUID user references and has no equivalent deep-link
    route. Returning ``None`` for those references keeps older installations
    from rendering a link that the panel cannot open.
    Prefer the browser-facing URL; retain the API URL for existing installations
    with no separate public URL. An invalid explicit public URL never falls back
    to an internal API address.
    """

    user_id = numeric_panel_user_id(panel_user_reference)
    raw_url = str(panel_public_url or "").strip() or str(panel_api_url or "").strip()
    if user_id is None or not raw_url:
        return None

    parsed = _panel_browser_base(raw_url)
    if parsed is None:
        return None
    return urlunsplit(parsed._replace(path=f"{parsed.path}/dashboard/open/user/{user_id}"))
