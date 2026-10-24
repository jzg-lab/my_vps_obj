"""Read-only, opt-in verification of the actual local Panel statistics contract."""

import asyncio
import os
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from bot.app.web.admin_console_nodes_panel import NodeInventoryReader
from bot.app.web.admin_console_nodes_schemas import ConsoleNodeTrafficPreset
from bot.app.web.admin_console_nodes_traffic import NodeTrafficReader, traffic_dates
from tests.qa.test_remnawave_panel_contract import _panel_service


def test_live_node_calendar_windows_use_actual_panel_statistics() -> None:
    assert urlsplit(os.environ["QA_REMNAWAVE_API_URL"]).hostname in {
        "127.0.0.1",
        "localhost",
        "::1",
    }
    assert Path(os.environ["QA_ENV_FILE"]).resolve() == (
        Path(__file__).resolve().parents[2] / ".env.project-dev"
    )

    async def run() -> None:
        panel = _panel_service()
        try:
            inventory = await NodeInventoryReader().read(panel, ttl_seconds=0)
            assert all(source.availability == "available" for source in inventory.sources)
            nodes = [inventory.node_out(node) for node in inventory.nodes.rows]
            identities = [node.id for node in nodes]
            reader = NodeTrafficReader()
            presets: tuple[ConsoleNodeTrafficPreset, ...] = ("today", "7d", "30d")
            for preset in presets:
                now = datetime.now(UTC)
                result = await reader.read(
                    panel,
                    preset=preset,
                    nodes=nodes,
                    inventory_complete=True,
                    ttl_seconds=0,
                    now=now,
                )
                assert result.availability in {"available", "partial"}
                assert result.error is None
                assert (result.start_date, result.end_date) == traffic_dates(preset, now)
                assert result.timezone == "UTC"
                assert result.inventory_nodes == len(identities)
                assert [node.id for node in nodes] == identities
                assert result.matched_nodes == sum(
                    node.window_traffic_quality == "reported" for node in nodes
                )
                for node in nodes:
                    if node.window_traffic_quality == "reported":
                        assert node.window_traffic_bytes is not None
                        assert 0 <= node.window_traffic_bytes <= 2**53 - 1
                    else:
                        assert node.window_traffic_quality == "missing"
                        assert node.window_traffic_bytes is None
        finally:
            await panel.close()

    asyncio.run(run())
