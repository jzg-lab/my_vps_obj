"""Allowlisted single-attempt resource writes using the existing redacted transport."""

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from bot.app.web.admin_console_resource_schemas import (
    ResourceChange,
    ResourceGroupChange,
    ResourceGroupCreate,
    ResourceHostChange,
    ResourceHostCreate,
    ResourceNodeChange,
    ResourceNodeCreate,
)
from bot.services.panel_api_contracts import PanelApiOperation, operation_contract
from bot.services.panel_api_service import PanelApiService
from bot.services.panel_dry_run_api_service import PanelDryRunApiService
from bot.services.resource_preview_panel import _metadata
from config.settings import Settings
from db.dal.user_services_dal import ServiceConflict


def resource_writes_enabled(panel: PanelApiService | None) -> bool:
    settings: object = getattr(panel, "settings", None)
    return (
        panel is not None
        and not isinstance(panel, PanelDryRunApiService)
        and isinstance(settings, Settings)
        and settings.panel_dry_run_enabled is False
    )


async def require_resource_panel(panel: PanelApiService | None) -> PanelApiService:
    if not resource_writes_enabled(panel):
        raise ServiceConflict("resource_dry_run", 409)
    assert panel is not None
    metadata, version = await _metadata(panel)
    if metadata.availability != "available" or version != "3.4.5":
        raise ServiceConflict("resource_panel_unsupported", 409)
    return panel


def creation_marker(operation_id: str, *, host: bool = False) -> str:
    return "OP_" + operation_id.upper() if host else "resource-op:" + operation_id


def _host_payload(values: dict[str, object]) -> dict[str, object]:
    output: dict[str, object] = {}
    for local, remote in (
        ("name", "remark"),
        ("address", "address"),
        ("port", "port"),
        ("node_ids", "nodes"),
        ("is_disabled", "isDisabled"),
        ("is_hidden", "isHidden"),
    ):
        if local in values:
            output[remote] = values[local]
    if "profile_id" in values:
        output["inbound"] = {
            "configProfileUuid": values["profile_id"],
            "configProfileInboundUuid": values["inbound_id"],
        }
    if "group_mode" in values:
        output["internalSquads"] = {"mode": values["group_mode"], "squads": values["group_ids"]}
    return output


def resource_payload(
    change: ResourceChange, operation_id: str
) -> tuple[PanelApiOperation, str, dict[str, object] | None]:
    if isinstance(change, ResourceNodeCreate):
        return (
            PanelApiOperation.NODE_CREATE,
            "/nodes",
            {
                "name": change.name,
                "address": change.address,
                "port": change.port,
                "note": creation_marker(operation_id),
                "configProfile": {
                    "activeConfigProfileUuid": str(change.profile_id),
                    "activeInbounds": [str(value) for value in change.inbound_ids],
                },
            },
        )
    if isinstance(change, (ResourceGroupChange, ResourceGroupCreate)):
        payload: dict[str, object] = {"inbounds": [str(value) for value in change.inbound_ids]}
        if isinstance(change, ResourceGroupCreate):
            payload["name"] = change.name
            return PanelApiOperation.GROUP_CREATE, "/internal-squads", payload
        payload["uuid"] = str(change.target_id)
        return PanelApiOperation.GROUP_UPDATE, "/internal-squads", payload
    if isinstance(change, ResourceHostCreate):
        payload = _host_payload(change.model_dump(mode="json"))
        payload["tags"] = [creation_marker(operation_id, host=True)]
        return PanelApiOperation.HOST_CREATE, "/hosts", payload
    if isinstance(change, ResourceHostChange):
        payload = _host_payload(change.patch.model_dump(mode="json", exclude_unset=True))
        payload["uuid"] = str(change.target_id)
        return PanelApiOperation.HOST_UPDATE, "/hosts", payload
    operation = {
        "node_enable": PanelApiOperation.NODE_ENABLE,
        "node_disable": PanelApiOperation.NODE_DISABLE,
        "node_restart": PanelApiOperation.NODE_RESTART,
    }[change.operation]
    suffix = change.operation.removeprefix("node_")
    return (
        operation,
        f"/nodes/{change.target_id}/actions/{suffix}",
        ({"forceRestart": change.force_restart} if suffix == "restart" else None),
    )


@dataclass(frozen=True)
class ResourceReceipt:
    result: Literal["unknown", "accepted", "rejected"]
    target_id: str | None = None


async def dispatch_resource(
    panel: PanelApiService, change: ResourceChange, operation_id: str
) -> ResourceReceipt:
    if not resource_writes_enabled(panel):
        return ResourceReceipt("rejected")
    operation, path, payload = resource_payload(change, operation_id)
    contract = operation_contract(operation)
    try:
        result = await panel._request_once(
            contract.method,
            path,
            operation=operation,
            log_full_response=False,
            preserve_http_status=True,
            **({"json": payload} if payload is not None else {}),
        )
        if not isinstance(result, dict):
            return ResourceReceipt("unknown")
        status = result.get("status_code")
        # A 4xx/5xx may follow a committed partial write; only authorization rejection
        # is known to happen before the pinned endpoint handler.
        if status in (401, 403):
            return ResourceReceipt("rejected")
        if (
            type(status) is not int
            or status not in contract.success_statuses
            or result.get("error")
        ):
            return ResourceReceipt("unknown")
        if change.operation == "node_restart":
            if status != 202:
                return ResourceReceipt("unknown")
            return ResourceReceipt("accepted", str(change.target_id))
        body: object = result.get("response")
        identity = body.get("uuid") if isinstance(body, dict) else None
        if not isinstance(identity, str):
            return ResourceReceipt("unknown")
        identity = str(UUID(identity))
        if isinstance(
            change, (ResourceNodeChange, ResourceHostChange, ResourceGroupChange)
        ) and identity != str(change.target_id):
            return ResourceReceipt("unknown")
        return ResourceReceipt("accepted", identity)
    except Exception:
        return ResourceReceipt("unknown")
