import { render } from "svelte/server";
import { describe, expect, it } from "vitest";
import ConsoleNodeTable from "../../admin/sections/nodes/ConsoleNodeTable.svelte";
import ConsoleNodeDetail from "../../admin/sections/nodes/ConsoleNodeDetail.svelte";
import ConsoleNodeSources from "../../admin/sections/nodes/ConsoleNodeSources.svelte";
import ConsoleServiceResourcesView from "../../admin/sections/nodes/ConsoleServiceResourcesView.svelte";
import { demoApiResponse } from "../webapp/mockApi/datasetApi";
import {
  consoleNodeFixture,
  consoleNodeDetailFixture,
  consoleServiceResourcesFixture,
  consoleNodeServiceFixture,
} from "./consoleNodesFixtures";

const at = (key: string) => key;
const currentUrl = "https://console.test/app/admin/nodes?nodes_q=HK&nodes_page=2&node_id=old";

describe("node inventory presentation", () => {
  it("resolves the linked customer through the default demo detail API", () => {
    const customer = consoleNodeServiceFixture.customer!;
    expect(consoleNodeDetailFixture.services[0].user_id).toBe(customer.user_id);
    expect(consoleNodeServiceFixture.service.user_id).toBe(customer.user_id);
    for (const id of [customer.user_id, customer.minishop_id]) {
      const path = `/admin/users/${id}`;
      expect(demoApiResponse(path, path, {}, {})).toMatchObject({ ok: true, user: customer });
    }
  });

  it("keeps absent or defaulted online counts unknown and displays reported traffic zero", () => {
    const html = render(ConsoleNodeTable, {
      props: {
        nodes: [
          consoleNodeFixture,
          {
            ...consoleNodeFixture,
            id: "zero",
            name: "Zero traffic node",
            status: "online",
            users_online: 0,
            users_online_quality: "unverified_zero",
            traffic_used_bytes: 0,
          },
        ],
        source: consoleNodeDetailFixture.sources[0],
        at,
      },
    }).body;
    expect(html).toMatch(/data-label="console_nodes_online">console_unknown/);
    expect(html).toMatch(/data-label="console_nodes_traffic">console_unknown/);
    expect(html).not.toMatch(/data-label="console_nodes_online">0/);
    expect(html).toMatch(/data-label="console_nodes_traffic">0 B/);
    expect(html).toContain("Zero traffic node");
    expect(html).toContain("console_nodes_status_unknown");
    expect(html).toContain("console_nodes_status_online");
  });

  it("does not render reported zero as a known traffic identity count", () => {
    const html = render(ConsoleNodeTable, {
      props: {
        nodes: [{ ...consoleNodeFixture, users_online: 0, users_online_quality: "reported" }],
        source: consoleNodeDetailFixture.sources[0],
        at,
      },
    }).body;
    expect(html).toMatch(/data-label="console_nodes_online">console_unknown/);
    expect(html).not.toMatch(/data-label="console_nodes_online">0/);
  });

  it.each(["source_stale", "request_failed"])(
    "keeps previous online evidence separate after %s",
    (mode) => {
      const html = render(ConsoleNodeTable, {
        props: {
          nodes: [
            {
              ...consoleNodeFixture,
              status: "online",
              users_online: 3,
              users_online_quality: "reported",
            },
          ],
          source: {
            ...consoleNodeDetailFixture.sources[0],
            availability: mode === "source_stale" ? "stale" : "available",
          },
          stale: mode === "request_failed",
          at,
        },
      }).body;
      expect(html).toContain("console_nodes_status_unknown");
      expect(html).toContain("console_nodes_previous_control");
      expect(html).toContain("console_stale");
      expect(html).toContain("2026-10-24 16:00");
      expect(html).not.toContain('data-variant="success"');
    }
  );

  it.each(["complete", "partial", "stale", "unavailable"] as const)(
    "announces %s coverage and individual source freshness",
    (coverage) => {
      const html = render(ConsoleNodeSources, {
        props: { coverage, sources: consoleNodeDetailFixture.sources, at },
      }).body;
      expect(html).toContain(`console_nodes_coverage_${coverage}`);
      expect(html).toContain("console_nodes_availability_unavailable");
      expect(html).toContain("console_nodes_read_time");
      expect(html).toContain('role="status"');
    }
  );

  it("marks retained source statuses stale after the whole request fails", () => {
    const html = render(ConsoleNodeSources, {
      props: { coverage: "stale", sources: [consoleNodeDetailFixture.sources[0]], stale: true, at },
    }).body;
    expect(html).toContain("console_nodes_availability_stale");
    expect(html).not.toContain("console_nodes_availability_available");
    expect(html).toContain("2026-10-24 16:00");
  });

  it("renders potential impact with unknown totals and actual service/customer URLs", () => {
    const html = render(ConsoleNodeDetail, {
      props: {
        api: async () => {
          throw new Error("SSR must not call the API");
        },
        detail: consoleNodeDetailFixture,
        at,
        currentUrl,
        routePrefix: "/app",
        page: 0,
        onPageChange: () => {},
        onBack: () => {},
        onOpenUserCard: () => {},
      },
    }).body;
    expect(html).toContain("console_nodes_association_scope");
    expect(html).toContain("console_nodes_incomplete_relations");
    expect(html).toMatch(/console_nodes_service_total: console_unknown/);
    expect(html).toContain(
      `/app/admin/services?nodes_q=HK&amp;nodes_page=2&amp;section=services&amp;service_id=${"a".repeat(32)}`
    );
    expect(html).toContain(
      `/app/admin/users/${consoleNodeServiceFixture.customer!.user_id}?nodes_q=HK&amp;nodes_page=2&amp;section=users`
    );
    expect(html).toContain("HK subscription entry");
    expect(html).toContain("Shared HK");
    expect(html).not.toContain("console_nodes_no_services");
  });

  it("links the service resources to a node, preserving node filters and service context", () => {
    const html = render(ConsoleServiceResourcesView, {
      props: {
        resources: consoleServiceResourcesFixture,
        at,
        currentUrl:
          "https://console.test/app/admin/services?nodes_q=HK&nodes_page=2&q=foreign&user_id=1",
        routePrefix: "/app",
      },
    }).body;
    const encodedHref = html.match(/href="([^"]+)"/)?.[1];
    expect(encodedHref).toBeDefined();
    const url = new URL(encodedHref!.replaceAll("&amp;", "&"));
    expect(url.pathname).toBe("/app/admin/nodes");
    expect(url.searchParams.get("node_id")).toBe(consoleNodeFixture.id);
    expect(url.searchParams.get("service_id")).toBe(consoleServiceResourcesFixture.service_id);
    expect(url.searchParams.get("nodes_q")).toBe("HK");
    expect(url.searchParams.get("nodes_page")).toBe("2");
    expect(url.searchParams.has("q")).toBe(false);
    expect(url.searchParams.has("user_id")).toBe(false);
    expect(html).toContain("console_nodes_resource_scope");
  });

  it("distinguishes confirmed absence from incomplete associations", () => {
    for (const coverage of ["complete", "partial"] as const) {
      const html = render(ConsoleServiceResourcesView, {
        props: {
          resources: { ...consoleServiceResourcesFixture, nodes: [], coverage },
          at,
          currentUrl,
        },
      }).body;
      expect(html).toContain(
        coverage === "complete"
          ? "console_nodes_no_resource_nodes"
          : "console_nodes_no_known_resource_nodes"
      );
    }
  });
});
