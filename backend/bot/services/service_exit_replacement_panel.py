"""A single-attempt PATCH receipt, without the legacy 202 -> readback completion fallback."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime

from bot.services.panel_api_compat import normalize_panel_user, numeric_panel_user_id
from bot.services.panel_api_contracts import PanelApiOperation
from bot.services.panel_api_service import PanelApiService
from bot.services.panel_dry_run_api_service import PanelDryRunApiService
from bot.services.resource_preview_panel import digest
from db.dal.user_services_dal import ServiceConflict


@dataclass(frozen=True)
class ReplacementPatch:
    reference: str
    payload: dict[str, object]


async def prepare_patch(
    panel: PanelApiService,
    reference: str,
    values: dict[str, object],
) -> ReplacementPatch:
    if isinstance(panel, PanelDryRunApiService):
        raise ServiceConflict("exit_replacement_panel_unsupported")
    compatibility = await panel.get_panel_api_compatibility()
    if compatibility.version != "3.4.5" or not await panel.panel_mutation_allowed(
        PanelApiOperation.USER_UPDATE, compatibility=compatibility
    ):
        raise ServiceConflict("exit_replacement_panel_unsupported")
    resolved = await panel.resolve_panel_user_reference(
        reference, PanelApiOperation.USER_UPDATE, compatibility=compatibility
    )
    identity = numeric_panel_user_id(resolved)
    if identity is None or not panel.base_url:
        raise ServiceConflict("panel_identity_conflict")
    return ReplacementPatch(reference, values | {"id": identity})


def _matches_field(key: str, actual: object, expected: object) -> bool:
    if key == "expireAt":
        if not isinstance(actual, str) or not isinstance(expected, str):
            return False
        try:
            observed = datetime.fromisoformat(actual)
            requested = datetime.fromisoformat(expected)
        except ValueError:
            return False
        return (
            observed.tzinfo is not None
            and requested.tzinfo is not None
            and observed.astimezone(UTC).isoformat(timespec="milliseconds")
            == requested.astimezone(UTC).isoformat(timespec="milliseconds")
        )
    if key == "activeInternalSquads":
        if not isinstance(actual, list) or not isinstance(expected, list):
            return False
        groups = [item.get("uuid") if isinstance(item, dict) else item for item in actual]
        return (
            all(isinstance(item, str) and item for item in groups + expected)
            and len(set(groups)) == len(groups)
            and len(set(expected)) == len(expected)
            and set(groups) == set(expected)
        )
    if type(expected) is int:
        return type(actual) is int and actual == expected
    return actual == expected


async def dispatch_patch(panel: PanelApiService, patch: ReplacementPatch) -> str | None:
    """Return a control-plane receipt digest only; no assertion about stopped flows/bytes.

    The legacy transport drops HTTP status for JSON bodies. Use its existing session,
    timeout and auth headers, but keep status here and never log a body or exception.
    """
    if isinstance(panel, PanelDryRunApiService):
        return None
    try:
        session = await panel._get_session()
        headers = await panel._prepare_headers()
        async with session.request(
            "PATCH",
            f"{panel.base_url.rstrip('/')}/users",
            headers=headers,
            json=patch.payload,
            allow_redirects=False,
        ) as response:
            body = await response.text()
            if response.status != 200:
                return None
            raw: object = json.loads(body)
            user = normalize_panel_user(raw.get("response") if isinstance(raw, dict) else None)
            if user is None or str(user.get("uuid")) != patch.reference:
                return None
            for key, value in patch.payload.items():
                if not _matches_field(key, user.get(key), value):
                    return None
            await panel._invalidate_user_cache(patch.reference)
            await panel._invalidate_all_users_cache()
            return digest([response.status, patch.payload, user])
    except Exception:
        return None
