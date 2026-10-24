import asyncio
from unittest.mock import patch

import pytest
from aiohttp import web
from aiohttp.test_utils import make_mocked_request

from bot.app.web.webapp.routes import setup_subscription_webapp_routes


@pytest.mark.parametrize(
    "path",
    [
        "/admin/console-overview",
        "/admin/console-operations?needs_attention=true",
        "/admin/services?section=services&service_id=7",
        "/admin/nodes?section=nodes&nodes_q=test&node_id=node-7",
        "/admin/node-resources",
        "/admin/advanced-maintenance",
        "/admin/advanced-maintenance?section=advanced-maintenance",
        "/admin/dedicated-exits?exits_page=1&exit_id=exit-7&exit_service_id=service-7",
    ],
)
def test_console_deep_links_use_the_core_shell(path: str) -> None:
    app = web.Application()
    setup_subscription_webapp_routes(app)
    request = make_mocked_request("GET", path, app=app)

    match = asyncio.run(app.router.resolve(request))

    assert match.handler.__name__ == "index_route"


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/api/admin/console/services"),
        ("GET", "/api/admin/console/operations"),
        ("GET", "/api/admin/console/services/" + "a" * 32),
        ("GET", "/api/admin/console/summary"),
        ("GET", "/api/admin/console/maintenance"),
        ("GET", "/api/admin/console/nodes"),
        ("GET", "/api/admin/console/nodes/00000000-0000-0000-0000-000000000001"),
        ("GET", "/api/admin/console/services/" + "a" * 32 + "/resources"),
        ("POST", "/api/admin/console/service-preflight"),
        ("GET", "/api/admin/console/services/" + "a" * 32 + "/diagnostics"),
        ("GET", "/api/admin/console/services/" + "a" * 32 + "/operations"),
        (
            "POST",
            "/api/admin/console/services/" + "a" * 32 + "/operations/" + "b" * 32 + "/retry",
        ),
        ("POST", "/api/admin/console/resources/preview"),
        ("GET", "/api/admin/console/resources/catalog"),
        ("POST", "/api/admin/console/resources/revalidate"),
        ("GET", "/api/admin/console/resources/operations"),
        ("GET", "/api/admin/console/resources/operations/" + "a" * 32),
        ("POST", "/api/admin/console/resources/operations"),
        ("POST", "/api/admin/console/resources/operations/" + "a" * 32 + "/retry"),
        ("POST", "/api/admin/console/resources/operations/" + "a" * 32 + "/reconcile"),
        ("POST", "/api/admin/console/resources/operations/" + "a" * 32 + "/evidence"),
        ("POST", "/api/admin/console/nodes/onboarding/deployment"),
        ("GET", "/api/admin/console/services/" + "a" * 32 + "/exit-replacement"),
        ("POST", "/api/admin/console/services/" + "a" * 32 + "/exit-replacement"),
        ("POST", "/api/admin/console/services/" + "a" * 32 + "/exit-replacement/confirm"),
        ("POST", "/api/admin/console/services/" + "a" * 32 + "/exit-replacement/evidence"),
    ],
)
@pytest.mark.parametrize("user_id", [None, 42])
def test_registered_console_routes_reject_unprivileged_requests(
    method: str, path: str, user_id: int | None
) -> None:
    app = web.Application()
    setup_subscription_webapp_routes(app)
    request = make_mocked_request(method, path, app=app)

    async def exercise() -> None:
        match = await app.router.resolve(request)
        assert match.handler.__name__.startswith("admin_console_")

        with (
            patch("bot.app.web.session.extract_authenticated_user_id", return_value=user_id),
            pytest.raises(web.HTTPException) as raised,
        ):
            await match.handler(request)

        assert raised.value.status == (401 if user_id is None else 403)

    asyncio.run(exercise())
