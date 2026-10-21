"""Retire upstream single-subscription entry points in the project web runtime."""

from aiohttp import web
from aiohttp.typedefs import Handler

from bot.app.web.response_helpers import json_response
from bot.app.web.session import extract_authenticated_user_id

SINGLE_SUBSCRIPTION_RETIRED: web.AppKey[bool] = web.AppKey("single_subscription_retired", bool)

_USER_GROUPS = (
    "/api/balance",
    "/api/devices",
    "/api/gifts",
    "/api/partner",
    "/api/payments",
    "/api/promo",
    "/api/subscription",
    "/api/subscription-guides",
    "/api/tariffs",
    "/api/trial",
    "/s",
)
_EXACT_PATHS = {
    "/api/payment-history",
    "/api/plans/viewed",
    "/api/referral/welcome-bonus/claim",
    "/api/extensions/checkout",
    "/api/extensions/orders",
    "/api/extensions/order",
    "/api/extensions/payment-methods",
    "/api/admin/sync",
    "/open-app",
}
_ADMIN_GROUPS = (
    "/api/admin/gifts",
    "/api/admin/payments",
    "/api/admin/promos",
    "/api/admin/tariffs",
    "/api/admin/partners",
    "/api/admin/partner-applications",
    "/api/admin/partner-withdrawals",
)
_ACCOUNT_ACTIONS = {
    "balance-adjustment",
    "balance-conversion",
    "reset-trial",
    "subscription-reissue",
    "squad-overrides",
    "squad-overrides/refresh",
    "extend",
    "tariff",
    "premium-override",
    "regular-traffic-override",
    "traffic-strategy",
    "hwid-device-limit",
    "traffic-grant",
}


def retired_single_subscription_route(method: str, path: str) -> bool:
    """Match canonical router paths, including parameter placeholders, not raw URLs."""
    if path in _EXACT_PATHS or any(
        path == group or path.startswith(group + "/") for group in _USER_GROUPS
    ):
        return True
    if method.upper() in {"GET", "HEAD", "OPTIONS"}:
        return False
    if any(path == group or path.startswith(group + "/") for group in _ADMIN_GROUPS):
        return True
    prefix = "/api/admin/users/{user_id}/"
    return path.startswith(prefix) and path.removeprefix(prefix) in _ACCOUNT_ACTIONS


@web.middleware
async def legacy_business_middleware(request: web.Request, handler: Handler) -> web.StreamResponse:
    resource = request.match_info.route.resource
    path = resource.canonical if resource is not None else ""
    if retired_single_subscription_route(request.method, path):
        if (
            path.startswith("/api/")
            and not path.startswith("/api/subscription-guides/public/")
            and extract_authenticated_user_id(request) is None
        ):
            return json_response({"ok": False, "error": "unauthorized"}, status=401)
        if path.startswith("/api/admin/") and not request.get("admin_authorized", False):
            return json_response({"ok": False, "error": "forbidden"}, status=403)
        return json_response({"ok": False, "error": "legacy_business_retired"}, status=410)
    return await handler(request)
