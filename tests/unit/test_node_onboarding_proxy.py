"""Actual proxy branches and standalone runtime imports, with offline upstream IO."""

from __future__ import annotations

import asyncio
import base64
import builtins
import json
import runpy
from pathlib import Path
from uuid import uuid4

import aiohttp
import pytest
from aiohttp import web
from aiohttp.test_utils import make_mocked_request

from tests.support import node_onboarding_live_node as harness
from tests.unit.test_node_onboarding_live_support import (
    OfflineNode,
    certificates,
    transport,
)
from tests.unit.test_node_onboarding_live_support import fixture_node as fixture_node
from tests.unit.test_node_onboarding_live_support import no_environment as no_environment


@pytest.fixture
def standalone(tmp_path: Path) -> dict[str, object]:
    runtime = tmp_path / "runtime.py"
    runtime.write_bytes(Path(harness.__file__).read_bytes())
    original = builtins.__import__

    def isolated_import(
        name: str,
        globals: dict[str, object] | None = None,
        locals: dict[str, object] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> object:
        assert name.split(".")[0] not in {"tests", "bot", "db", "config"}
        return original(name, globals, locals, fromlist, level)

    return runpy.run_path(
        str(runtime),
        run_name="uc07_standalone",
        init_globals={"__builtins__": {**vars(builtins), "__import__": isolated_import}},
    )


def test_standalone_proxy_satisfies_guard_without_trusting_client_forwarding_headers(
    standalone: dict[str, object],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = "/opaque%2Fsecret?q=%2f%2B"
    harness.private_bytes(
        tmp_path / "request.json",
        json.dumps({"url": "https://127.0.0.1:3010" + target}).encode(),
    )
    _, session = transport(monkeypatch, body=b"actual-upstream-subscription")
    response_context = session.get.return_value

    def guarded_upstream(url: object, *, headers: dict[str, str], allow_redirects: bool):
        assert str(url) == harness.UPSTREAM + target and allow_redirects is False
        # subscription-page 7.2.6 rejects requests missing either of these headers.
        assert headers["X-Forwarded-For"] == "127.0.0.1"
        assert headers["X-Forwarded-Proto"] == "https"
        assert headers["Host"] == harness.LOCAL_AUTHORITY
        assert "Authorization" not in headers and "Cookie" not in headers
        assert "Forwarded" not in headers
        return response_context

    session.get.side_effect = guarded_upstream
    request = make_mocked_request(
        "GET",
        target,
        headers={
            "Host": harness.LOCAL_AUTHORITY,
            "X-Forwarded-For": "203.0.113.8, secret",
            "X-Forwarded-Proto": "http",
            "Forwarded": "for=203.0.113.8;proto=http",
            "Authorization": "Bearer secret",
            "Cookie": "secret=cookie",
        },
    )
    proxy = standalone["proxy_subscription"]
    assert callable(proxy)
    response = asyncio.run(proxy(request, tmp_path))
    assert isinstance(response, web.Response)
    assert response.status == 200 and response.body == b"actual-upstream-subscription"
    assert "X-UC07-Proxy-Failure" not in response.headers
    session.get.assert_called_once()


@pytest.mark.parametrize(
    "error,kind",
    [
        (aiohttp.ServerDisconnectedError("https://private/secret"), "ServerDisconnectedError"),
        (TimeoutError("https://private/secret"), "TimeoutError"),
        (NameError("private_secret_name"), "NameError"),
        (ModuleNotFoundError("private_secret_module"), "ModuleNotFoundError"),
        (RuntimeError("https://private/secret"), "UnexpectedError"),
    ],
)
def test_proxy_failures_reach_safe_diagnostics_through_strict_tls_fetch(
    standalone: dict[str, object],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    kind: str,
) -> None:
    directory = tmp_path / "tls"
    certificates(directory, harness.tls_material())
    harness.private_bytes(directory / "request.json", b'{"url":"https://127.0.0.1:3010/secret"}')
    _, upstream = transport(monkeypatch, body=b"unused")
    upstream.get.side_effect = error
    proxy, fetch = standalone["proxy_subscription"], standalone["fetch_in_container"]
    assert callable(proxy) and callable(fetch)
    request = make_mocked_request("GET", "/secret", headers={"Host": harness.LOCAL_AUTHORITY})
    response = asyncio.run(proxy(request, directory))
    assert isinstance(response, web.Response)
    assert response.status == 502 and response.text == "local_subscription_proxy_failed"
    assert response.headers["X-UC07-Proxy-Failure"] == kind
    assert "secret" not in str(dict(response.headers))
    _, downstream = transport(monkeypatch, body=b"local_subscription_proxy_failed", status=502)
    downstream.get.return_value.__aenter__.return_value.headers = response.headers
    asyncio.run(fetch(directory))
    saved = json.loads((directory / "response.json").read_bytes())
    assert saved["tls_verified"] is True and saved["status"] == 502
    assert saved["proxy_failure_type"] == kind
    assert "secret" not in json.dumps(saved)
    assert downstream.get.call_args.kwargs["ssl"].check_hostname is True
    assert downstream.get.call_args.kwargs["allow_redirects"] is False


@pytest.mark.parametrize("kind", ["ServerDisconnectedError", "private-secret-class"])
def test_fetch_report_only_projects_allowlisted_proxy_failure(
    fixture_node: OfflineNode,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
) -> None:
    tls = harness.SubscriptionTLS(fixture_node)
    asyncio.run(tls.start())
    original = fixture_node.docker

    async def response_transport(*args: str) -> str:
        if args[0] == "cp" and args[1].endswith(":/tmp/onboarding-tls/response.json"):
            harness.private_bytes(
                Path(args[2]),
                json.dumps(
                    {
                        "status": 502,
                        "content_type": "text/plain",
                        "tls_verified": True,
                        "body_base64": base64.b64encode(
                            b"local_subscription_proxy_failed"
                        ).decode(),
                        "proxy_failure_type": kind,
                    }
                ).encode(),
            )
            return "copied"
        return await original(*args)

    monkeypatch.setattr(fixture_node, "docker", response_transport)
    with pytest.raises(harness.SubscriptionEvidenceError, match="subscription_checkpoint_failed"):
        asyncio.run(
            tls.fetch(
                "https://127.0.0.1:3010/secret",
                target=fixture_node,
                identity=str(uuid4()),
            )
        )
    report = json.loads((fixture_node.directory / "report.json").read_bytes())["onboarding_tls"]
    assert report["tls_verified"] is True and report["http_status"] == 502
    assert report["body_bytes"] == 31 and report["failure_code"] == "subscription_http_status"
    if kind in harness.FAILURE_CODES:
        assert report["proxy_failure_type"] == kind
        assert report["proxy_failure_code"] == "upstream_disconnected"
    else:
        assert "proxy_failure_type" not in report and "proxy_failure_code" not in report
    assert "secret" not in json.dumps(report)
    asyncio.run(tls.cleanup())
