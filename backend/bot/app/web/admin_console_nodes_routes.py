"""Administrator-only inventory and potential impact; GET never reconciles state."""

import re
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from aiohttp import web
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from bot.app.web.admin_api_impl.auth import _require_admin_user_id
from bot.app.web.admin_api_impl.common import _error, _ok
from bot.app.web.admin_console_nodes_panel import NodeInventory, NodeInventoryReader
from bot.app.web.admin_console_nodes_schemas import (
    ConsoleNodeDetailOut,
    ConsoleNodeServiceOut,
    ConsoleNodesListOut,
    ConsoleNodeTrafficPreset,
    ConsoleServiceResourcesOut,
)
from bot.app.web.admin_console_nodes_traffic import NodeTrafficReader
from bot.app.web.context import get_panel_service, get_session_factory, get_settings
from bot.app.web.route_contracts import (
    ADMIN_SECURITY,
    RouteContract,
    ok_envelope_for,
    register_contract,
)
from bot.services.user_service_access import service_ready_for_delivery, service_status
from config.service_plans import ServicePlanTerms
from db.dal.admin_console_nodes_dal import (
    ServiceResourceRow,
    read_service_resources,
    service_group_ids,
)

_INVENTORY_READER = web.AppKey("console_node_inventory", NodeInventoryReader)
_TRAFFIC_READER = web.AppKey("console_node_traffic", NodeTrafficReader)


class ConsoleNodesQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    q: str = Field(default="", max_length=200)
    status: Literal["all", "online", "offline", "unknown"] = "all"
    page: int = Field(default=0, ge=0, le=1_000_000)
    page_size: int = Field(default=25, ge=1, le=200)
    traffic_window: ConsoleNodeTrafficPreset = "today"


class ConsoleNodeServicesQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page: int = Field(default=0, ge=0, le=1_000_000)
    page_size: int = Field(default=25, ge=1, le=200)
    traffic_window: ConsoleNodeTrafficPreset = "today"


async def _inventory(request: web.Request) -> NodeInventory:
    return await request.app[_INVENTORY_READER].read(
        get_panel_service(request),
        ttl_seconds=int(get_settings(request).ADMIN_PANEL_STATS_CACHE_TTL_SECONDS or 0),
    )


async def admin_console_nodes_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    if len(request.query.getall("traffic_window", [])) > 1:
        return _error(400, "invalid_console_nodes_query")
    try:
        query = ConsoleNodesQuery.model_validate(dict(request.query))
    except ValidationError:
        return _error(400, "invalid_console_nodes_query")
    inventory = await _inventory(request)
    nodes = [inventory.node_out(node) for node in inventory.nodes.rows]
    traffic = await request.app[_TRAFFIC_READER].read(
        get_panel_service(request),
        preset=query.traffic_window,
        nodes=nodes,
        inventory_complete=inventory.nodes.source.availability == "available",
        ttl_seconds=int(get_settings(request).ADMIN_PANEL_STATS_CACHE_TTL_SECONDS or 0),
    )
    if query.q:
        needle = query.q.casefold()
        nodes = [
            node
            for node in nodes
            if needle
            in " ".join(
                (node.id, node.name, node.address or "", node.country_code or "")
            ).casefold()
        ]
    if query.status != "all":
        nodes = [node for node in nodes if node.status == query.status]
    nodes.sort(key=lambda node: (node.name.casefold(), node.id))
    start = query.page * query.page_size
    result = ConsoleNodesListOut(
        nodes=nodes[start : start + query.page_size],
        total=len(nodes) if inventory.nodes.source.availability == "available" else None,
        page=query.page,
        page_size=query.page_size,
        coverage=inventory.coverage,
        sources=inventory.sources,
        cache_ttl_seconds=int(get_settings(request).ADMIN_PANEL_STATS_CACHE_TTL_SECONDS or 0),
        traffic=traffic,
    )
    response = _ok(result.model_dump(mode="json"))
    response.headers["Cache-Control"] = "private, no-store"
    return response


def _service_out(row: ServiceResourceRow, *, now: datetime) -> ConsoleNodeServiceOut:
    service, connection, resource, user = row
    return ConsoleNodeServiceOut(
        id=service.id,
        name=ServicePlanTerms.model_validate(service.terms).name,
        user_id=user.user_id,
        status=service_status(service, connection, resource, banned=bool(user.is_banned), now=now),
        connection_state=connection.state if connection else None,
        currently_eligible=bool(
            connection
            and service_ready_for_delivery(
                service,
                connection,
                resource,
                banned=bool(user.is_banned),
                now=now,
            )
        ),
    )


async def admin_console_node_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    if len(request.query.getall("traffic_window", [])) > 1:
        return _error(400, "invalid_console_node_query")
    try:
        node_id = str(UUID(request.match_info["node_id"]))
        query = ConsoleNodeServicesQuery.model_validate(dict(request.query))
    except (ValueError, ValidationError):
        return _error(400, "invalid_console_node_query")
    inventory = await _inventory(request)
    node = next((node for node in inventory.nodes.rows if str(node.uuid) == node_id), None)
    if node is None:
        if inventory.nodes.source.availability != "available":
            return _error(503, "node_inventory_unavailable")
        return _error(404, "node_not_found")
    nodes = [inventory.node_out(item) for item in inventory.nodes.rows]
    traffic = await request.app[_TRAFFIC_READER].read(
        get_panel_service(request),
        preset=query.traffic_window,
        nodes=nodes,
        inventory_complete=inventory.nodes.source.availability == "available",
        ttl_seconds=int(get_settings(request).ADMIN_PANEL_STATS_CACHE_TTL_SECONDS or 0),
    )
    now = datetime.now(UTC)
    group_ids = inventory.node_groups(node)
    async with get_session_factory(request)() as session:
        rows = await read_service_resources(session, group_ids=group_ids)
    coverage = inventory.scope_coverage(rows)
    complete = coverage == "complete"
    start = query.page * query.page_size
    result = ConsoleNodeDetailOut(
        node=next(item for item in nodes if item.id == node_id),
        hosts=inventory.node_hosts(node),
        groups=inventory.group_refs(group_ids),
        services=[_service_out(row, now=now) for row in rows[start : start + query.page_size]],
        service_total=len(rows) if complete else None,
        customer_total=len({row[3].user_id for row in rows}) if complete else None,
        page=query.page,
        page_size=query.page_size,
        associations_complete=complete,
        coverage=coverage,
        sources=inventory.sources,
        local_observed_at=now,
        traffic=traffic,
    )
    response = _ok(result.model_dump(mode="json"))
    response.headers["Cache-Control"] = "private, no-store"
    return response


async def admin_console_service_resources_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    service_id = request.match_info["service_id"]
    if re.fullmatch(r"[0-9a-f]{32}", service_id) is None:
        return _error(400, "invalid_service_id")
    if request.query:
        return _error(400, "invalid_console_resources_query")
    async with get_session_factory(request)() as session:
        rows = await read_service_resources(session, service_id=service_id)
    if not rows:
        return _error(404, "service_not_found")
    service, connection, resource, _ = rows[0]
    inventory = await _inventory(request)
    group_ids = service_group_ids(service, resource)
    nodes = [node for node in inventory.nodes.rows if group_ids & inventory.node_groups(node)]
    hosts = {
        host.id: host for node in nodes for host in inventory.node_hosts(node, groups=group_ids)
    }
    known_groups = {str(squad.uuid) for squad in inventory.squads.rows}
    coverage = inventory.scope_coverage(rows)
    if coverage == "complete" and (
        group_ids - known_groups
        or any(host.permits(group_ids) is None for host in inventory.hosts.rows)
    ):
        coverage = "partial"
    now = datetime.now(UTC)
    service_out = _service_out(rows[0], now=now)
    result = ConsoleServiceResourcesOut(
        service_id=service_id,
        status=service_out.status,
        connection_state=connection.state if connection else None,
        currently_eligible=service_out.currently_eligible,
        configured_group_ids=sorted(group_ids),
        groups=inventory.group_refs(group_ids),
        nodes=[inventory.node_out(node) for node in nodes],
        hosts=list(hosts.values()),
        coverage=coverage,
        sources=inventory.sources,
        local_observed_at=now,
    )
    response = _ok(result.model_dump(mode="json"))
    response.headers["Cache-Control"] = "private, no-store"
    return response


def setup_admin_console_nodes_routes(app: web.Application) -> None:
    app[_INVENTORY_READER] = NodeInventoryReader()
    app[_TRAFFIC_READER] = NodeTrafficReader()
    for handler, model in (
        (admin_console_nodes_route, ConsoleNodesListOut),
        (admin_console_node_route, ConsoleNodeDetailOut),
        (admin_console_service_resources_route, ConsoleServiceResourcesOut),
    ):
        register_contract(
            handler.__name__,
            RouteContract(
                response_schema=ok_envelope_for(model),
                models=(model,),
                security=ADMIN_SECURITY,
            ),
        )
    app.router.add_get("/api/admin/console/nodes", admin_console_nodes_route)
    app.router.add_get("/api/admin/console/nodes/{node_id}", admin_console_node_route)
    app.router.add_get(
        "/api/admin/console/services/{service_id}/resources", admin_console_service_resources_route
    )
