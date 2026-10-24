"""Per-account service summaries from persisted independent-service records."""

from datetime import datetime
from typing import Literal

from pydantic import Field

from bot.app.web.http_contracts import HttpResponseModel


class ConsoleCustomerServicesOut(HttpResponseModel):
    total: int = Field(
        ge=0,
        description="当前归属此账号的独立服务总数，包含已取消服务，不包含已解除归属的归档服务。"
        "同一套餐多次开通的服务分别计数。",
    )
    by_status: dict[
        Literal[
            "active", "pending", "paused", "cancelled", "expired", "exhausted", "account_banned"
        ],
        int,
    ] = Field(
        description="按全局服务列表规则划分的互斥业务状态计数，所有状态均返回，无对应服务时为零。"
        "account_banned 表示账号限制而非单份服务故障；active 不代表已验证实时连通性。",
    )
    sync_error: int = Field(
        ge=0,
        description="存在交付、权益同步、用量采样错误或连接状态为错误的服务数，"
        "与全局 sync_error 筛选口径一致。各同步及未观测集合可能重叠，不可相加为总异常数。",
    )
    sync_pending: int = Field(ge=0, description="权益同步待处理的服务数，待处理不等同于失败。")
    cycle_pending: int = Field(ge=0, description="等待月度周期切换的服务数。")
    sync_unobserved: int = Field(ge=0, description="本地尚无成功权益同步确认记录的服务数。")
    usage_unobserved: int = Field(ge=0, description="本地尚无成功用量采样记录的服务数。")
    oldest_sync_confirmed_at: datetime | None
    latest_sync_confirmed_at: datetime | None
    oldest_usage_sync_at: datetime | None
    latest_usage_sync_at: datetime | None
    observed_at: datetime = Field(
        description="本次本地聚合读取的 UTC 时间，复用客户列表缓存时保留原值。成功时间戳表示"
        "已持久化的历史证据，不代表即时远端读取或客户活跃；空值表示本账号统计范围内无成功观测。",
    )
    source: Literal["local_independent_service_records"] = "local_independent_service_records"
    scope: Literal["current_owner_excludes_archived"] = "current_owner_excludes_archived"
    activity: Literal["not_collected"] = Field(
        default="not_collected",
        description="尚未采集可靠的账号级在线状态或最近活跃观测。",
    )
