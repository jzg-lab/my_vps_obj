import { describe, expect, it } from "vitest";
import {
  nodePreviewChange,
  nodePreviewUrl,
  readNodePreviewRoute,
} from "./resourcePreviewNavigation";

const source =
  "https://console.test/app/admin/nodes?section=nodes&node_id=node-a&nodes_q=HK&nodes_status=offline&nodes_page=2&nodes_related_page=3&users_q=owner#inventory";
describe("node resource preview URL context", () => {
  it("round trips the draft and a service deep link without losing inventory context", () => {
    const route = {
      open: true,
      operation: "node_restart" as const,
      forceRestart: true,
      serviceId: "a".repeat(32),
    };
    const url = nodePreviewUrl(source, route, "/app");
    expect(url.pathname).toBe("/app/admin/nodes");
    expect(readNodePreviewRoute(url.search)).toEqual(route);
    for (const key of [
      "node_id",
      "nodes_q",
      "nodes_status",
      "nodes_page",
      "nodes_related_page",
      "users_q",
    ])
      expect(url.searchParams.get(key)).toBe(new URL(source).searchParams.get(key));
    expect(url.hash).toBe("#inventory");
    expect(nodePreviewChange("node-a", route)).toEqual({
      operation: "node_restart",
      target_id: "node-a",
      force_restart: true,
    });
  });

  it("returns from service to the exact preview, then closes only owned parameters", () => {
    const route = {
      open: true,
      operation: "node_disable" as const,
      forceRestart: false,
      serviceId: "",
    };
    const preview = nodePreviewUrl(source, route, "/app");
    const service = nodePreviewUrl(preview.href, { ...route, serviceId: "service" }, "/app");
    expect(nodePreviewUrl(service.href, route, "/app").href).toBe(preview.href);
    expect(nodePreviewUrl(preview.href, { ...route, open: false }, "/app").href).toBe(source);
    expect(nodePreviewChange("node-a", { ...route, open: false })).toBeNull();
  });

  it("rejects unknown operations and never restores a confirmation from the URL", () => {
    const route = readNodePreviewRoute(
      "?resource_preview=node&resource_action=execute&resource_force=1&confirmed=1"
    );
    expect(route.operation).toBe("");
    expect(route.forceRestart).toBe(false);
    expect(nodePreviewChange("node-a", route)).toBeNull();
    expect(
      readNodePreviewRoute("?resource_action=node_restart&resource_service_id=ignored")
    ).toEqual({ open: false, operation: "", forceRestart: false, serviceId: "" });
  });

  it("drops force restart from non-restart operations", () => {
    const route = readNodePreviewRoute(
      "?resource_preview=node&resource_action=node_enable&resource_force=1"
    );
    expect(route.forceRestart).toBe(false);
    expect(
      nodePreviewUrl(source, { ...route, forceRestart: true }, "/app").searchParams.has(
        "resource_force"
      )
    ).toBe(false);
  });
});
