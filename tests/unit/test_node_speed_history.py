from datetime import UTC, datetime, timedelta

from bot.services.node_speed_history import RETENTION, parse_speed_rows


def test_parse_speed_rows_keeps_missing_direction_as_unknown() -> None:
    rows = parse_speed_rows(
        {"nodes": [{"uuid": "node-1", "stats": {"interface": {"rxBytesPerSec": 12}}}]},
        datetime(2026, 10, 26, tzinfo=UTC),
    )
    assert len(rows) == 1
    assert rows[0].rx_bytes_per_second == 12
    assert rows[0].tx_bytes_per_second is None


def test_retention_is_exactly_one_day() -> None:
    assert timedelta(hours=24) == RETENTION
