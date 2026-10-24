import { describe, expect, it } from "vitest";
import {
  consoleNodeDetailPath,
  consoleNodesListPath,
  nodeRelatedUrl,
  nodesRouteUrl,
  readNodesRoute,
} from "./consoleNodesNavigation";

describe("nodes navigation", () => {
  it.each(["today", "7d", "30d"])("sends the %s window to both generated API paths", (window) => {
    const route = readNodesRoute(
      `?nodes_traffic_window=${window}&nodes_page=2&nodes_related_page=3&nodes_q=HK%26EU&nodes_status=offline&node_id=node%2Fa%2Bb`
    );
    const list = new URL(consoleNodesListPath(route), "https://fixture.test");
    expect(list.pathname).toBe("/admin/console/nodes");
    expect(Object.fromEntries(list.searchParams)).toEqual({
      q: "HK&EU",
      status: "offline",
      page: "2",
      page_size: "25",
      traffic_window: window,
    });
    const detail = new URL(consoleNodeDetailPath(route), "https://fixture.test");
    expect(detail.pathname).toBe("/admin/console/nodes/node%2Fa%2Bb");
    expect(Object.fromEntries(detail.searchParams)).toEqual({
      page: "3",
      page_size: "25",
      traffic_window: window,
    });
  });

  it.each(["today", "7d", "30d"])(
    "preserves the %s UTC window through detail/back and service navigation",
    (window) => {
      const route = readNodesRoute(`?nodes_traffic_window=${window}&nodes_q=HK&nodes_page=2`);
      expect(route.trafficWindow).toBe(window);
      const detail = nodesRouteUrl("https://console.test/admin/nodes", {
        ...route,
        nodeId: "node-1",
      });
      const back = nodesRouteUrl(detail.href, { ...route, nodeId: "" });
      expect(readNodesRoute(back.search)).toEqual(route);
      const service = nodeRelatedUrl(detail.href, { serviceId: "service-1" });
      expect(readNodesRoute(service.search).trafficWindow).toBe(window);
    }
  );

  it.each(["custom", "", "90d", "TODAY"])(
    "normalizes unsupported window %s to today UTC",
    (window) => {
      expect(readNodesRoute(`?nodes_traffic_window=${window}`).trafficWindow).toBe("today");
    }
  );

  it("retains service scope, literal IDs, filters and route prefix through detail/back", () => {
    const route = readNodesRoute(
      "?service_id=svc%2B1&nodes_q=HK%26EU&nodes_status=offline&nodes_page=2"
    );
    const detail = nodesRouteUrl(
      "https://console.test/prefix/admin/nodes?lang=zh#content",
      {
        ...route,
        nodeId: "node/a+b",
      },
      "/prefix"
    );
    expect(detail.pathname).toBe("/prefix/admin/nodes");
    expect(detail.searchParams.get("lang")).toBe("zh");
    expect(detail.hash).toBe("#content");
    expect(readNodesRoute(detail.search)).toEqual({ ...route, nodeId: "node/a+b" });
    const back = nodesRouteUrl(detail.href, { ...route, nodeId: "" }, "/prefix");
    expect(back.searchParams.has("node_id")).toBe(false);
    expect(readNodesRoute(back.search)).toEqual(route);
  });

  it.each(["-1", "NaN", "1.5", "Infinity", "1000001"])("rejects invalid page %s", (page) => {
    expect(readNodesRoute(`?nodes_page=${page}`).page).toBe(0);
    expect(readNodesRoute(`?nodes_related_page=${page}`).relatedPage).toBe(0);
  });

  it("normalizes unsupported status and keeps independent relation pagination", () => {
    expect(
      readNodesRoute("?nodes_status=unmanaged&nodes_page=2&nodes_related_page=3")
    ).toMatchObject({ status: "all", page: 2, relatedPage: 3 });
    const route = readNodesRoute("?nodes_status=unknown&nodes_related_page=3");
    expect(
      readNodesRoute(
        nodesRouteUrl("https://console.test/admin/nodes?user_id=1&q=other&page=7", route).search
      )
    ).toEqual(route);
    expect(
      nodesRouteUrl(
        "https://console.test/admin/nodes?user_id=1&q=other&page=7",
        route
      ).searchParams.has("user_id")
    ).toBe(false);
  });

  it("opens the existing customer path and drops conflicting foreign filters", () => {
    const url = nodeRelatedUrl(
      "https://console.test/admin/nodes?node_id=n1&service_id=s1&q=old&nodes_q=HK&nodes_status=unknown&nodes_page=2&mock=services&theme_preview=dark",
      { userId: "ms_123" },
      "/app"
    );
    expect(url.pathname).toBe("/app/admin/users/ms_123");
    expect(url.searchParams.get("section")).toBe("users");
    expect(url.searchParams.has("service_id")).toBe(false);
    expect(url.searchParams.has("q")).toBe(false);
    expect(url.searchParams.get("nodes_q")).toBe("HK");
    expect(url.searchParams.get("nodes_status")).toBe("unknown");
    expect(url.searchParams.get("nodes_page")).toBe("2");
    expect(url.searchParams.get("mock")).toBe("services");
    expect(url.searchParams.get("theme_preview")).toBe("dark");
  });

  it("opens a service without inheriting another customer's filter", () => {
    const url = nodeRelatedUrl("https://console.test/admin/nodes?user_id=42&node_id=n1&page=8", {
      serviceId: "svc/a+b",
    });
    expect(url.pathname).toBe("/admin/services");
    expect(url.searchParams.get("section")).toBe("services");
    expect(url.searchParams.get("service_id")).toBe("svc/a+b");
    expect(url.searchParams.has("user_id")).toBe(false);
    expect(url.searchParams.has("page")).toBe(false);
  });
});
