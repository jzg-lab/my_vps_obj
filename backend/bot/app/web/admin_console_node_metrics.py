"""Project optional Node metrics without letting malformed fields discard inventory."""

import math
from typing import Literal, cast

from bot.app.web.admin_console_nodes_schemas import ConsoleNodeSystemField, ConsoleNodeSystemOut

type _Path = tuple[str | int, ...]
type _ValueState = Literal["present", "missing", "invalid"]

_FIELDS: dict[ConsoleNodeSystemField, _Path] = {
    "cpu_cores": ("info", "cpus"),
    "cpu_model": ("info", "cpuModel"),
    "memory_total_bytes": ("info", "memoryTotal"),
    "memory_free_bytes": ("stats", "memoryFree"),
    "memory_used_bytes": ("stats", "memoryUsed"),
    "load_1m": ("stats", "loadAvg", 0),
    "load_5m": ("stats", "loadAvg", 1),
    "load_15m": ("stats", "loadAvg", 2),
    "uptime_seconds": ("stats", "uptime"),
    "interface_name": ("stats", "interface", "interface"),
    "rx_bytes_per_second": ("stats", "interface", "rxBytesPerSec"),
    "tx_bytes_per_second": ("stats", "interface", "txBytesPerSec"),
    "rx_total_bytes": ("stats", "interface", "rxTotal"),
    "tx_total_bytes": ("stats", "interface", "txTotal"),
}


def _read(value: object, path: _Path) -> tuple[_ValueState, object]:
    for part in path:
        if value is None:
            return "missing", None
        if isinstance(part, int):
            if not isinstance(value, list) or len(value) != 3:
                return "invalid", None
            value = value[part]
        elif isinstance(value, dict):
            value = cast(dict[str, object], value).get(part)
        else:
            return "invalid", None
    return ("missing" if value is None else "present"), value


def _valid_value(name: ConsoleNodeSystemField, value: object) -> bool:
    if name in {"cpu_model", "interface_name"}:
        return isinstance(value, str) and bool(value.strip()) and len(value) <= 256
    if name == "cpu_cores":
        return type(value) is int and 0 < value <= 2**53 - 1
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value) and value >= 0
    except OverflowError:
        return False


def parse_node_system(value: object) -> ConsoleNodeSystemOut:
    values: dict[str, object] = {}
    invalid: list[ConsoleNodeSystemField] = []
    for name, path in _FIELDS.items():
        state, raw = _read(value, path)
        # Node uses this literal when os.cpus() provides no CPU model.
        if name == "cpu_model" and raw == "unknown":
            values[name] = None
            continue
        if state == "invalid" or (state == "present" and not _valid_value(name, raw)):
            invalid.append(name)
            values[name] = None
        else:
            values[name] = raw.strip() if isinstance(raw, str) else raw
    values["invalid_fields"] = invalid
    return ConsoleNodeSystemOut.model_validate(values)
