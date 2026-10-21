"""Confirm idempotent remote deletion without treating an outage as absence."""

import logging

logger = logging.getLogger(__name__)


async def is_panel_user_confirmed_absent(panel_service: object, panel_uuid: str) -> bool:
    lookup = getattr(panel_service, "get_user_by_uuid_lookup", None)
    if not callable(lookup):
        return False

    try:
        result = await lookup(panel_uuid, log_response=False)
    except Exception:
        logger.warning(
            "Could not verify whether panel user %s is absent.",
            panel_uuid,
            exc_info=True,
        )
        return False

    return isinstance(result, dict) and result.get("not_found") is True
