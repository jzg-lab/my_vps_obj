"""No network: a real replacement adapter against a fake aiohttp response."""

import asyncio
import json
import logging
from types import TracebackType
from unittest.mock import AsyncMock, Mock, patch

import pytest

from bot.services.panel_api_service import PanelApiService
from bot.services.panel_dry_run_api_service import PanelDryRunApiService
from bot.services.service_exit_replacement_panel import (
    ReplacementPatch,
    dispatch_patch,
    prepare_patch,
)
from config.settings import Settings
from db.dal.user_services_dal import ServiceConflict

SECRET = "FAKE_PRIVATE_KEY_AND_PASSWORD"


class Reply:
    def __init__(self, status: int, body: str) -> None:
        self.status = status
        self.body = body

    async def text(self) -> str:
        return self.body

    async def __aenter__(self) -> "Reply":
        return self

    async def __aexit__(
        self,
        _type: type[BaseException] | None,
        _value: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        return None


@pytest.mark.parametrize(
    "status,body,accepted",
    [
        (
            200,
            {
                "response": {
                    "id": 7,
                    "status": "DISABLED",
                    "activeInternalSquads": [],
                    "password": SECRET,
                }
            },
            True,
        ),
        (
            202,
            {
                "response": {
                    "id": 7,
                    "status": "DISABLED",
                    "activeInternalSquads": [],
                    "password": SECRET,
                }
            },
            False,
        ),
        (204, None, False),
        (500, {"config": {"privateKey": SECRET}}, False),
        (400, {"password": SECRET}, False),
        (200, {"response": {"id": 8, "status": "DISABLED", "activeInternalSquads": []}}, False),
        (200, {"response": {"id": 7, "status": "ACTIVE", "activeInternalSquads": []}}, False),
    ],
)
def test_completion_receipt_requires_synchronous_exact_response(
    status: int,
    body: object,
    accepted: bool,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    panel = PanelApiService(
        Settings(
            POSTGRES_USER="test",
            POSTGRES_PASSWORD="test",
            BOT_TOKEN="1234567890:AA_secret_bot_token_value",
            _env_file=None,
        )
    )
    panel.base_url = "https://panel.invalid/api"
    fake = Mock()
    fake.request.return_value = Reply(status, json.dumps(body) if body is not None else "")
    with (
        patch.object(panel, "_get_session", AsyncMock(return_value=fake)),
        patch.object(panel, "_prepare_headers", AsyncMock(return_value={"Authorization": SECRET})),
        patch.object(panel, "_invalidate_user_cache", AsyncMock()),
        patch.object(panel, "_invalidate_all_users_cache", AsyncMock()),
        patch.object(panel, "get_user_by_uuid_lookup", AsyncMock()) as lookup,
    ):
        result = asyncio.run(
            dispatch_patch(
                panel,
                ReplacementPatch("7", {"id": 7, "status": "DISABLED", "activeInternalSquads": []}),
            )
        )
        assert (result is not None) == accepted
        assert SECRET not in caplog.text and SECRET not in str(result)
        lookup.assert_not_awaited()
        fake.request.assert_called_once()


def test_transport_timeout_is_unknown_and_dryrun_cannot_be_bypassed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    settings = Settings(
        POSTGRES_USER="test",
        POSTGRES_PASSWORD="test",
        BOT_TOKEN="1234567890:AA_secret_bot_token_value",
        _env_file=None,
    )
    panel = PanelApiService(settings)
    panel.base_url = "https://panel.invalid/api"
    fake = Mock()
    fake.request.side_effect = TimeoutError(SECRET)
    with (
        patch.object(panel, "_get_session", AsyncMock(return_value=fake)),
        patch.object(panel, "_prepare_headers", AsyncMock(return_value={})),
        patch.object(panel, "get_user_by_uuid_lookup", AsyncMock()) as lookup,
    ):
        assert asyncio.run(dispatch_patch(panel, ReplacementPatch("7", {"id": 7}))) is None
        fake.request.assert_called_once()
        lookup.assert_not_awaited()
    assert SECRET not in caplog.text
    dry = PanelDryRunApiService(settings)
    with patch.object(dry, "_get_session", AsyncMock()) as get_session:
        with pytest.raises(ServiceConflict, match="panel_unsupported"):
            asyncio.run(prepare_patch(dry, "7", {"status": "ACTIVE"}))
        assert asyncio.run(dispatch_patch(dry, ReplacementPatch("7", {"id": 7}))) is None
        get_session.assert_not_awaited()


@pytest.mark.parametrize(
    "updates,accepted",
    [
        ({"expireAt": "2026-11-24T00:00:00.123Z"}, True),
        ({"expireAt": "2026-11-24T00:00:00.123+00:00"}, True),
        ({"expireAt": "2026-11-24T08:00:00.123+08:00"}, True),
        ({"expireAt": "2026-11-24T00:00:00.123999Z"}, True),
        ({"expireAt": "2026-11-24T00:00:00.124Z"}, False),
        ({"expireAt": "2026-11-24T00:00:00.123+01:00"}, False),
        ({"expireAt": "2026-11-24T00:00:00.123"}, False),
        ({"expireAt": SECRET}, False),
        ({"expireAt": None}, False),
        ({"id": 8}, False),
        ({"uuid": "8"}, False),
        ({"id": True, "uuid": "7"}, False),
        ({"trafficLimitBytes": 2}, False),
        ({"trafficLimitBytes": True}, False),
        ({"trafficLimitBytes": 1.0}, False),
        ({"trafficLimitBytes": "1"}, False),
        ({"trafficLimitStrategy": "DAY"}, False),
        ({"activeInternalSquads": ["group-b", "group-a"]}, True),
        ({"activeInternalSquads": [{"uuid": "group-b"}, {"uuid": "group-a"}]}, True),
        ({"activeInternalSquads": ["group-a"]}, False),
        ({"activeInternalSquads": ["group-a", "group-c"]}, False),
        ({"activeInternalSquads": ["group-a", "group-b", "group-c"]}, False),
        ({"activeInternalSquads": ["group-a", "group-b", "group-b"]}, False),
        ({"activeInternalSquads": ["group-a", {"uuid": True}]}, False),
        ({"activeInternalSquads": ["group-a", {"uuid": ["group-b"]}]}, False),
        ({"activeInternalSquads": None}, False),
        ({"externalSquadUuid": "foreign"}, False),
    ],
)
def test_raw_receipt_checks_time_identity_limits_and_groups(
    updates: dict[str, object], accepted: bool, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    panel = PanelApiService(
        Settings(
            POSTGRES_USER="test",
            POSTGRES_PASSWORD="test",
            BOT_TOKEN="1234567890:AA_secret_bot_token_value",
            _env_file=None,
        )
    )
    panel.base_url = "https://panel.invalid/api"
    payload: dict[str, object] = {
        "id": 7,
        "status": "DISABLED",
        "expireAt": "2026-11-24T00:00:00.123+00:00",
        "trafficLimitBytes": 1,
        "trafficLimitStrategy": "NO_RESET",
        "externalSquadUuid": None,
        "activeInternalSquads": ["group-a", "group-b"],
    }
    response = {"response": payload | updates | {"password": SECRET, "privateKey": SECRET}}
    fake = Mock()
    fake.request.return_value = Reply(200, json.dumps(response))
    with (
        patch.object(panel, "_get_session", AsyncMock(return_value=fake)),
        patch.object(panel, "_prepare_headers", AsyncMock(return_value={"Authorization": SECRET})),
        patch.object(panel, "_invalidate_user_cache", AsyncMock()) as invalidate,
        patch.object(panel, "_invalidate_all_users_cache", AsyncMock()) as invalidate_all,
        patch.object(panel, "get_user_by_uuid_lookup", AsyncMock()) as lookup,
    ):
        result = asyncio.run(dispatch_patch(panel, ReplacementPatch("7", payload)))
        assert (result is not None) == accepted
        assert invalidate.await_count == int(accepted)
        assert invalidate_all.await_count == int(accepted)
        lookup.assert_not_awaited()
        fake.request.assert_called_once_with(
            "PATCH",
            "https://panel.invalid/api/users",
            headers={"Authorization": SECRET},
            json=payload,
            allow_redirects=False,
        )
    assert SECRET not in caplog.text and SECRET not in str(result)
