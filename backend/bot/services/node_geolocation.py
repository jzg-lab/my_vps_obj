"""Best-effort country lookup of node management addresses, never exit verification."""

import asyncio
import ipaddress
import socket
from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, datetime
from time import monotonic

import aiohttp

from config.country_codes import COUNTRY_CODES


@dataclass(frozen=True)
class NodeCountry:
    country_code: str | None = None
    ip: str | None = None
    looked_up_at: datetime | None = None


class NodeCountryReader:
    """Bounded process cache; new address keys cannot inherit an old country's flag."""

    def __init__(self) -> None:
        self._cache: OrderedDict[str, tuple[float, NodeCountry]] = OrderedDict()
        self._semaphore = asyncio.Semaphore(4)

    async def read(self, address: str | None) -> NodeCountry:
        if not address:
            return NodeCountry()
        address = address.strip().lower()
        async with self._semaphore:
            cached = self._cache.get(address)
            if cached and cached[0] > monotonic():
                self._cache.move_to_end(address)
                return cached[1]
            result = NodeCountry()
            literal = False
            try:
                async with asyncio.timeout(3):
                    try:
                        addresses = {ipaddress.ip_address(address)}
                        literal = True
                    except ValueError:
                        records = await asyncio.get_running_loop().getaddrinfo(
                            address, None, type=socket.SOCK_STREAM
                        )
                        addresses = {ipaddress.ip_address(record[4][0]) for record in records}
                    # DNS pools can span countries; do not pick an arbitrary location.
                    if len(addresses) == 1:
                        ip = addresses.pop()
                        if ip.is_global and not ip.is_multicast:
                            code = await self._lookup(str(ip))
                            if code:
                                result = NodeCountry(code, str(ip), datetime.now(UTC))
            except (aiohttp.ClientError, OSError, TimeoutError, ValueError):
                pass
            ttl = 86400 if result.country_code and literal else 300
            self._cache[address] = (monotonic() + ttl, result)
            self._cache.move_to_end(address)
            while len(self._cache) > 1024:
                self._cache.popitem(last=False)
            return result

    async def _lookup(self, ip: str) -> str | None:
        # Only the validated public IP is sent; never contact a node-supplied URL.
        async with (
            aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=2)) as session,
            session.get(f"https://api.country.is/{ip}", allow_redirects=False) as response,
        ):
            if response.status != 200:
                return None
            payload: object = await response.json()
        if not isinstance(payload, dict) or payload.get("ip") != ip:
            return None
        country: object = payload.get("country")
        return country if isinstance(country, str) and country in COUNTRY_CODES else None
