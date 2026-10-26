"""Read-only node inventory and entitlement relations, without panel credentials."""

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import Field

from bot.app.web.http_contracts import HttpResponseModel

type ConsoleNodesCoverage = Literal["complete", "partial", "stale", "unavailable"]
type ConsoleNodeStatus = Literal["online", "offline", "unknown"]
type ConsoleNodeTrafficPreset = Literal["today", "7d", "30d"]
type ConsoleNodeSystemField = Literal[
    "cpu_cores",
    "cpu_model",
    "memory_total_bytes",
    "memory_free_bytes",
    "memory_used_bytes",
    "load_1m",
    "load_5m",
    "load_15m",
    "uptime_seconds",
    "interface_name",
    "rx_bytes_per_second",
    "tx_bytes_per_second",
    "rx_total_bytes",
    "tx_total_bytes",
]
type _SystemNumber = Annotated[float, Field(strict=True, ge=0, allow_inf_nan=False)]


class ConsoleNodeSystemOut(HttpResponseModel):
    """Node 所见系统与默认网卡；不是 Panel 主机或服务计费指标。"""

    cpu_cores: Annotated[int, Field(strict=True, ge=1)] | None = None
    cpu_model: str | None = None
    memory_total_bytes: _SystemNumber | None = None
    memory_free_bytes: _SystemNumber | None = None
    memory_used_bytes: _SystemNumber | None = None
    load_1m: _SystemNumber | None = Field(
        default=None, description="1 分钟系统负载，不是 CPU 百分比"
    )
    load_5m: _SystemNumber | None = Field(
        default=None, description="5 分钟系统负载，不是 CPU 百分比"
    )
    load_15m: _SystemNumber | None = Field(
        default=None, description="15 分钟系统负载，不是 CPU 百分比"
    )
    uptime_seconds: _SystemNumber | None = Field(default=None, description="操作系统运行秒数")
    interface_name: str | None = None
    rx_bytes_per_second: _SystemNumber | None = Field(
        default=None, description="默认网卡接收 B/s，名义 1 秒差分，实际窗口未提供"
    )
    tx_bytes_per_second: _SystemNumber | None = Field(
        default=None, description="默认网卡发送 B/s，名义 1 秒差分，实际窗口未提供"
    )
    rx_total_bytes: _SystemNumber | None = None
    tx_total_bytes: _SystemNumber | None = None
    sampled_at: None = Field(
        default=None, description="上游未提供样本时间，不使用 Panel 读取时间替代"
    )
    invalid_fields: list[ConsoleNodeSystemField] = Field(
        default_factory=list, description="非法字段已置空；其他空值表示未提供，零值保持为零"
    )


class ConsoleNodeSourceOut(HttpResponseModel):
    source: Literal["nodes", "hosts", "internal_squads"]
    availability: Literal[
        "available", "partial", "stale", "unavailable", "unsupported", "unconfigured"
    ]
    attempted_at: datetime
    last_success_at: datetime | None = None
    error: (
        Literal["request_failed", "invalid_response", "not_supported", "not_configured"] | None
    ) = None


class ConsoleResourceRefOut(HttpResponseModel):
    id: str
    name: str | None


class ConsoleTrafficDayOut(HttpResponseModel):
    date: date
    bytes: int | None = Field(default=None, ge=0)


class ConsoleSpeedSampleOut(HttpResponseModel):
    sampled_at: datetime
    rx_bytes_per_second: float | None = Field(default=None, ge=0)
    tx_bytes_per_second: float | None = Field(default=None, ge=0)


class ConsoleNodeTrafficWindowOut(HttpResponseModel):
    """UTC 日范围；完整 UUID 覆盖不证明历史采样连续，也不改变北京时间服务账期。"""

    preset: ConsoleNodeTrafficPreset
    start_date: date
    end_date: date
    start_at: datetime
    end_at: datetime
    timezone: Literal["UTC"] = "UTC"
    boundaries: Literal["inclusive_start_and_end"] = "inclusive_start_and_end"
    source: Literal["remnawave_bandwidth_stats_nodes_series"] = (
        "remnawave_bandwidth_stats_nodes_series"
    )
    unit: Literal["bytes"] = "bytes"
    direction: Literal["outbound_upload_plus_download_unmultiplied"] = Field(
        default="outbound_upload_plus_download_unmultiplied",
        description="3.4.5 历史统计为 Node outbound 上传加下载，未乘消费倍率，不等同跟踪累计计数",
    )
    history_completeness: Literal["unknown_not_service_billing"] = "unknown_not_service_billing"
    availability: Literal["available", "partial", "stale", "unavailable", "unconfigured"]
    attempted_at: datetime
    last_success_at: datetime | None = Field(
        description="统计接口成功读取时间，不是最后流量样本时间；含今天的窗口尚未结束"
    )
    inventory_nodes: int | None
    matched_nodes: int
    error: Literal["request_failed", "invalid_response", "not_configured"] | None = None
    cache_ttl_seconds: int


class ConsoleNodeOut(HttpResponseModel):
    id: str
    name: str
    address: str | None
    country_code: str | None
    status: ConsoleNodeStatus = Field(description="管理连接状态，不证明真实代理路径可用")
    is_disabled: bool | None
    is_connecting: bool | None
    last_status_change_at: datetime | None
    observed_at: datetime | None = Field(description="Panel 清单成功读取时间，不是源采样时间")
    observation_basis: Literal["panel_read_time_sample_time_unavailable"] = (
        "panel_read_time_sample_time_unavailable"
    )
    profile_id: str | None
    inbound_ids: list[str]
    groups: list[ConsoleResourceRefOut]
    users_online: int | None = Field(
        description="Panel 最近流量采集报告的身份数，不是实时客户、设备或连接数；零值无法核实"
    )
    users_online_quality: Literal["reported", "missing", "unverified_zero"] = Field(
        default="missing",
        description="上游零值也可能来自采集失败或缺缓存；系统指标存在不能证明身份统计成功",
    )
    system: ConsoleNodeSystemOut = Field(default_factory=ConsoleNodeSystemOut)
    online_scope: Literal["panel_reported_identities_not_unique_customers"] = (
        "panel_reported_identities_not_unique_customers"
    )
    traffic_used_bytes: int | None
    traffic_tracking_enabled: bool | None
    traffic_reset_day: int | None
    traffic_scope: Literal["panel_node_tracking_period_not_service_billing"] = (
        "panel_node_tracking_period_not_service_billing"
    )
    traffic_unit: Literal["bytes"] = "bytes"
    traffic_window: Literal["panel_tracking_counter_boundaries_unavailable"] = (
        "panel_tracking_counter_boundaries_unavailable"
    )
    window_traffic_bytes: int | None = None
    window_traffic_quality: Literal["reported", "missing", "invalid"] = "missing"
    daily_traffic: list[ConsoleTrafficDayOut] = Field(default_factory=list)
    speed_history: list[ConsoleSpeedSampleOut] = Field(default_factory=list)


class ConsoleHostOut(ConsoleResourceRefOut):
    inbound_id: str
    node_ids: list[str]
    is_disabled: bool | None
    is_hidden: bool | None


class ConsoleNodesListOut(HttpResponseModel):
    nodes: list[ConsoleNodeOut]
    total: int | None
    page: int
    page_size: int
    coverage: ConsoleNodesCoverage
    sources: list[ConsoleNodeSourceOut]
    cache_ttl_seconds: int
    traffic: ConsoleNodeTrafficWindowOut | None = None


class ConsoleNodeServiceOut(HttpResponseModel):
    id: str
    name: str
    user_id: int
    status: str
    connection_state: str | None
    currently_eligible: bool


class ConsoleNodeDetailOut(HttpResponseModel):
    node: ConsoleNodeOut
    hosts: list[ConsoleHostOut]
    groups: list[ConsoleResourceRefOut]
    services: list[ConsoleNodeServiceOut]
    service_total: int | None
    customer_total: int | None
    page: int
    page_size: int
    association_basis: Literal["persisted_service_scope_not_live_connections"] = (
        "persisted_service_scope_not_live_connections"
    )
    associations_complete: bool
    current_connections: None = None
    coverage: ConsoleNodesCoverage
    sources: list[ConsoleNodeSourceOut]
    local_observed_at: datetime
    traffic: ConsoleNodeTrafficWindowOut | None = None


class ConsoleServiceResourcesOut(HttpResponseModel):
    service_id: str
    status: str
    connection_state: str | None
    currently_eligible: bool
    configured_group_ids: list[str]
    groups: list[ConsoleResourceRefOut]
    nodes: list[ConsoleNodeOut]
    hosts: list[ConsoleHostOut]
    association_basis: Literal["persisted_service_scope_not_live_connections"] = (
        "persisted_service_scope_not_live_connections"
    )
    remote_authorization_verified: Literal[False] = False
    coverage: ConsoleNodesCoverage
    sources: list[ConsoleNodeSourceOut]
    local_observed_at: datetime
