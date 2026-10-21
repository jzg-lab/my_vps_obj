import logging

from aiohttp import web

from bot.app.web.context import (
    get_optional_subscription_service,
    get_panel_service,
    get_session_factory,
    get_settings,
)
from bot.app.web.request_parsing import parse_body_or_400
from bot.app.web.service_schemas import AccountAccessSyncOut
from bot.services.account_access_sync import set_account_ban, synchronize_access_after_commit
from db.dal.user_services_dal import ServiceConflict
from db.service_models import AccountAccessSync

from .auth import _require_admin_user_id
from .common import _error, _ok, _serialize_user
from .schemas import AdminUserBanBody
from .users_listing import _invalidate_after_admin_user_mutation

logger = logging.getLogger(__name__)


async def admin_user_ban_route(request: web.Request) -> web.Response:
    actor_id = _require_admin_user_id(request)
    target_id = int(request.match_info["user_id"])
    body = await parse_body_or_400(request, AdminUserBanBody)
    desired = bool(body.banned)

    settings = get_settings(request)
    panel_service = get_panel_service(request)
    if panel_service is None:
        subscription_service = get_optional_subscription_service(request)
        panel_service = getattr(subscription_service, "panel_service", None)
    async_session_factory = get_session_factory(request)
    async with async_session_factory() as session:
        try:
            user = await set_account_ban(
                session, user_id=target_id, actor_id=actor_id, banned=desired
            )
        except ServiceConflict as exc:
            await session.rollback()
            return _error(exc.status, exc.code)
        await session.commit()
        await session.refresh(user)
        result = _serialize_user(user)
        await synchronize_access_after_commit(session, target_id, panel_service)
        job = await session.get(AccountAccessSync, target_id)
        sync_result = AccountAccessSyncOut.from_job(job)
    try:
        await _invalidate_after_admin_user_mutation(settings, target_id)
    except Exception:
        logger.exception("Saved account ban cache invalidation failed for user %s", target_id)
    return _ok({"user": result, "access_sync": sync_result.model_dump(mode="json")})
