"""Local-business metric contracts; missing observations remain nullable."""

from datetime import datetime
from typing import Literal

from pydantic import Field

from bot.app.web.http_contracts import HttpResponseModel
from bot.app.web.service_schemas import UserServiceOut
from config.service_periods import as_utc
from config.service_plans import ServicePlanTerms
from db.dal.admin_console_services_dal import ServiceDetailRow
from db.service_models import ServiceConnection


class ConsoleCustomerOut(HttpResponseModel):
    user_id: int | None
    minishop_id: str | None
    username: str | None
    email: str | None
    first_name: str | None
    last_name: str | None
    is_banned: bool | None


class ConsoleServiceOut(HttpResponseModel):
    service: UserServiceOut
    customer: ConsoleCustomerOut

    @classmethod
    def from_row(cls, row: ServiceDetailRow) -> "ConsoleServiceOut":
        service, connection, resource, user = row
        return cls(
            service=UserServiceOut.from_orm_service(
                service, connection, resource, banned=bool(user and user.is_banned)
            ),
            customer=ConsoleCustomerOut(
                user_id=user.user_id if user else None,
                minishop_id=user.minishop_id if user else None,
                username=user.username if user else None,
                email=user.email if user else None,
                first_name=user.first_name if user else None,
                last_name=user.last_name if user else None,
                is_banned=bool(user.is_banned) if user else None,
            ),
        )


class ConsoleServiceListOut(HttpResponseModel):
    services: list[ConsoleServiceOut]
    total: int
    page: int
    page_size: int
    observed_at: datetime
    expiring_within_days: int


class ConsoleConnectionOut(HttpResponseModel):
    panel_user_uuid: str | None
    last_error: str | None
    attempted_at: datetime | None
    sync_attempted_at: datetime | None
    usage_attempted_at: datetime | None
    revoked_at: datetime | None

    @classmethod
    def from_connection(cls, connection: ServiceConnection) -> "ConsoleConnectionOut":
        return cls(
            panel_user_uuid=connection.panel_user_uuid,
            last_error=connection.last_error,
            attempted_at=as_utc(connection.attempted_at) if connection.attempted_at else None,
            sync_attempted_at=as_utc(connection.sync_attempted_at)
            if connection.sync_attempted_at
            else None,
            usage_attempted_at=as_utc(connection.usage_attempted_at)
            if connection.usage_attempted_at
            else None,
            revoked_at=as_utc(connection.revoked_at) if connection.revoked_at else None,
        )


class ConsoleServiceDetailOut(ConsoleServiceOut):
    connection: ConsoleConnectionOut | None
    terms: ServicePlanTerms


class ConsoleCustomersMetric(HttpResponseModel):
    total: int
    with_services: int
    banned: int
    source: Literal["business_accounts"] = "business_accounts"


class ConsoleServicesMetric(HttpResponseModel):
    total: int
    by_status: dict[str, int]
    entitlement_valid: int
    delivery_ready: int = Field(
        description=(
            "本地权益有效、连接身份已就绪且已观测，且没有待同步或同步错误；不代表实时连通性探测通过。"
        )
    )
    archived: int
    source: Literal["nonarchived_services"] = "nonarchived_services"


class ConsoleUsageMetric(HttpResponseModel):
    confirmed_used_bytes: int | None = Field(
        description=(
            "现存账号服务有确认样本的各自当前周期用量之和，可能混合月度与总量周期；"
            "不是全站本月或今日流量，采集失败时仍可包含上次确认值"
        )
    )
    services_total: int
    services_sampled: int = Field(description="具有最后确认用量时间的服务数，不保证当前采集成功")
    services_with_errors: int
    oldest_sample_at: datetime | None
    latest_sample_at: datetime | None
    availability: Literal["available", "partial", "unknown"] = Field(
        description="确认样本覆盖和采集错误状态，不代表样本实时或采样连续"
    )
    source: Literal["persisted_service_usage"] = "persisted_service_usage"
    scope: Literal["current_period_upload_plus_download_business_payload"] = (
        "current_period_upload_plus_download_business_payload"
    )
    unit: Literal["bytes"] = "bytes"
    freshness: Literal["last_confirmed_observation"] = "last_confirmed_observation"


class ConsoleHealthMetric(HttpResponseModel):
    delivery_pending: int
    delivery_failed: int
    sync_pending: int
    sync_failed: int
    usage_failed: int
    usage_unobserved: int
    cycle_pending: int
    account_sync_pending: int
    account_sync_failed: int
    latest_success_at: datetime | None = Field(
        description=(
            "最近持久化的服务权益同步确认时间；不是用量采样或账号同步成功时间，"
            "也不证明所有服务同步成功。"
        )
    )
    latest_attempt_at: datetime | None
    oldest_pending_since: datetime | None = None
    pending_time_unavailable_reason: Literal["enqueue_time_not_recorded"] = (
        "enqueue_time_not_recorded"
    )
    source: Literal["local_service_and_account_sync_records"] = (
        "local_service_and_account_sync_records"
    )
    scope: Literal["including_archived_services"] = "including_archived_services"


class ConsoleExitsMetric(HttpResponseModel):
    total: int
    available: int
    occupied: int
    pending_verification: int
    pending_reclaim: int
    disabled: int
    unverified_total: int
    source: Literal["dedicated_exit_inventory"] = "dedicated_exit_inventory"
    overlap: Literal["pending_reclaim_subset_of_occupied_disabled_may_overlap"] = (
        "pending_reclaim_subset_of_occupied_disabled_may_overlap"
    )


class ConsoleSummaryOut(HttpResponseModel):
    observed_at: datetime
    customers: ConsoleCustomersMetric
    services: ConsoleServicesMetric
    usage: ConsoleUsageMetric
    health: ConsoleHealthMetric
    exits: ConsoleExitsMetric
    refresh_mode: Literal["read_only_local_records"] = "read_only_local_records"
    timezone: Literal["Asia/Shanghai"] = "Asia/Shanghai"
