from datetime import date

from bot.app.web.admin_console_service_traffic import parse_service_traffic


def test_service_traffic_keeps_daily_zero_and_node_totals() -> None:
    start = date(2026, 10, 20)
    payload = {
        "categories": ["2026-10-20", "2026-10-21"],
        "sparklineData": [0, 4],
        "series": [
            {
                "uuid": "10000000-0000-0000-0000-000000000001",
                "total": 4,
                "data": [0, 4],
            }
        ],
    }
    result = parse_service_traffic(payload, "service-1", start, date(2026, 10, 21))
    assert [day.bytes for day in result.days] == [0, 4]
    assert result.nodes[0].bytes == 4
    assert result.availability == "available"
