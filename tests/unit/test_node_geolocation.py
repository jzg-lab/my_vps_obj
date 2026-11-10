"""Country enrichment stays bounded and never probes node-provided addresses."""

import asyncio
import socket
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import aiohttp

from bot.services.node_geolocation import NodeCountryReader


class NodeGeolocationTests(IsolatedAsyncioTestCase):
    async def test_slow_provider_is_cancelled_and_returns_unknown(self) -> None:
        cancelled = asyncio.Event()

        async def slow_lookup(ip: str) -> str:
            try:
                await asyncio.sleep(10)
                return "US"
            finally:
                cancelled.set()

        reader = NodeCountryReader()
        with patch.object(reader, "_lookup", slow_lookup):
            assert (await reader.read("8.8.8.8")).country_code is None
        assert cancelled.is_set()

    async def test_concurrent_reads_share_cache_and_cache_size_is_bounded(self) -> None:
        reader = NodeCountryReader()
        lookup = AsyncMock(return_value="US")
        with patch.object(reader, "_lookup", lookup):
            results = await asyncio.gather(*(reader.read("8.8.8.8") for _ in range(16)))
            assert all(item.country_code == "US" for item in results)
            lookup.assert_awaited_once()
            for index in range(1030):
                await reader.read(f"11.0.{index // 256}.{index % 256}")
            assert len(reader._cache) == 1024

    async def test_caches_success_and_failure_and_changes_country_with_address(self) -> None:
        reader = NodeCountryReader()
        lookup = AsyncMock(side_effect=["US", "JP", None, "DE"])
        with patch.object(reader, "_lookup", lookup):
            first = await reader.read("8.8.8.8")
            assert first.country_code == "US" and first.ip == "8.8.8.8"
            assert first.looked_up_at is not None
            assert await reader.read("8.8.8.8") == first
            assert (await reader.read("1.1.1.1")).country_code == "JP"
            assert (await reader.read("9.9.9.9")).country_code is None
            assert (await reader.read("9.9.9.9")).country_code is None
            assert lookup.await_count == 3
            with patch("bot.services.node_geolocation.monotonic", return_value=10**20):
                assert (await reader.read("8.8.8.8")).country_code == "DE"
        assert len(reader._cache) == 3

    async def test_private_special_and_ambiguous_addresses_are_not_sent_to_provider(self) -> None:
        reader = NodeCountryReader()
        lookup = AsyncMock(return_value="US")
        records = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("1.1.1.1", 0)),
        ]
        with patch.object(reader, "_lookup", lookup):
            for address in (None, "", "127.0.0.1", "10.0.0.1", "::1", "192.0.2.1", "224.0.0.1"):
                assert (await reader.read(address)).country_code is None
            with patch.object(
                asyncio.get_running_loop(), "getaddrinfo", AsyncMock(return_value=records)
            ):
                assert (await reader.read("pool.example")).country_code is None
            with patch.object(
                asyncio.get_running_loop(), "getaddrinfo", AsyncMock(side_effect=OSError)
            ):
                assert (await reader.read("unresolved.example")).country_code is None
        lookup.assert_not_awaited()

    async def test_resolves_domains_and_supports_ipv6_without_sending_hostnames(self) -> None:
        reader = NodeCountryReader()
        records = [(socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("2606:4700:4700::1111", 0, 0, 0))]
        lookup = AsyncMock(return_value="AU")
        with (
            patch.object(reader, "_lookup", lookup),
            patch.object(
                asyncio.get_running_loop(), "getaddrinfo", AsyncMock(return_value=records)
            ),
        ):
            assert (await reader.read("node.example")).ip == "2606:4700:4700::1111"
            assert (await reader.read("2606:4700:4700::1111")).country_code == "AU"
        assert lookup.await_count == 2
        lookup.assert_awaited_with("2606:4700:4700::1111")

    async def test_failed_lookup_stays_unknown_and_is_cached(self) -> None:
        for error in (TimeoutError(), aiohttp.ClientError(), ValueError()):
            with self.subTest(error=error):
                reader = NodeCountryReader()
                lookup = AsyncMock(side_effect=error)
                with patch.object(reader, "_lookup", lookup):
                    assert (await reader.read("8.8.8.8")).country_code is None
                    assert (await reader.read("8.8.8.8")).country_code is None
                lookup.assert_awaited_once()

    async def test_provider_contract_and_fixed_https_destination(self) -> None:
        cases: list[tuple[int, object, str | None]] = [
            (200, {"ip": "8.8.8.8", "country": "US"}, "US"),
            (200, {"ip": "1.1.1.1", "country": "US"}, None),
            (200, {"ip": "8.8.8.8", "country": "XX"}, None),
            (200, {"ip": "8.8.8.8", "country": 123}, None),
            (200, [], None),
            (302, {"ip": "8.8.8.8", "country": "US"}, None),
            (429, {}, None),
        ]
        for status, payload, expected in cases:
            with self.subTest(status=status, payload=payload):
                response = Mock(status=status, json=AsyncMock(return_value=payload))
                session = MagicMock()
                session.get.return_value.__aenter__ = AsyncMock(return_value=response)
                factory = MagicMock()
                factory.return_value.__aenter__ = AsyncMock(return_value=session)
                with patch("bot.services.node_geolocation.aiohttp.ClientSession", factory):
                    assert await NodeCountryReader()._lookup("8.8.8.8") == expected
                session.get.assert_called_once_with(
                    "https://api.country.is/8.8.8.8", allow_redirects=False
                )
