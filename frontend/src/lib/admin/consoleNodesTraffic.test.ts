import { readFileSync } from "node:fs";
import { render } from "svelte/server";
import { describe, expect, it } from "vitest";
import ConsoleNodesSection from "../../admin/sections/ConsoleNodesSection.svelte";
import ConsoleNodeTable from "../../admin/sections/nodes/ConsoleNodeTable.svelte";
import ConsoleNodeDetail from "../../admin/sections/nodes/ConsoleNodeDetail.svelte";
import NodeTrafficWindow from "../../admin/sections/nodes/NodeTrafficWindow.svelte";
import {
  consoleNodeFixture,
  consoleNodeDetailFixture,
  consoleNodeTrafficFixture,
} from "./consoleNodesFixtures";
import type { ConsoleNode, ConsoleNodeTraffic, ConsoleNodesTranslate } from "./consoleNodesTypes";
import { nodeTrafficDate, nodeWindowTrafficQuality } from "./consoleNodesTraffic";

const at: ConsoleNodesTranslate = (key, params) =>
  params
    ? `${key}[${Object.entries(params)
        .map(([key, value]) => `${key}=${value}`)
        .join(";")}]`
    : key;
const reported: ConsoleNode = {
  ...consoleNodeFixture,
  traffic_used_bytes: 4096,
  window_traffic_bytes: 0,
  window_traffic_quality: "reported",
};

function windowCell(html: string): string {
  return html.match(/<td[^>]*data-window-quality[\s\S]*?<\/td>/)?.[0] ?? "";
}

describe("node traffic window consumers", () => {
  it("renders the existing selector in the actual nodes section without making SSR requests", () => {
    const html = render(ConsoleNodesSection, {
      props: {
        api: async () => {
          throw new Error("SSR must not read the API");
        },
        at,
        onOpenUserCard: () => {},
      },
    }).body;
    expect(html).toContain('aria-label="console_nodes_window_label"');
    expect(html).toContain("console_nodes_window_today");
    expect(html).toContain("admin-select-wrap");
    expect(html).not.toContain("data-traffic-boundaries");
  });

  it("displays a reported zero separately from the preserved cumulative traffic", () => {
    const html = render(ConsoleNodeTable, {
      props: { nodes: [reported], traffic: consoleNodeTrafficFixture, at },
    }).body;
    expect(windowCell(html)).toContain('data-window-quality="reported"');
    expect(windowCell(html)).toContain("0 B");
    expect(html).toMatch(/data-label="console_nodes_traffic">4 KiB/);
    expect(html).toContain("console_nodes_window_traffic");
    const resourcesTable = render(ConsoleNodeTable, { props: { nodes: [reported], at } }).body;
    expect(resourcesTable).not.toContain("data-window-quality");
  });

  it("uses the same window metric in the actual node detail consumer", () => {
    const html = render(ConsoleNodeDetail, {
      props: {
        api: async () => {
          throw new Error("SSR must not read the API");
        },
        detail: { ...consoleNodeDetailFixture, node: reported, traffic: consoleNodeTrafficFixture },
        at,
        currentUrl: "https://fixture.test/admin/nodes?nodes_traffic_window=7d",
        page: 0,
        onPageChange: () => {},
        onBack: () => {},
        onOpenUserCard: () => {},
        onMetadataSaved: () => {},
      },
    }).body;
    expect(windowCell(html)).toContain("0 B");
    expect(html).toContain("nodes_traffic_window=7d");
    expect(html).toContain("console_nodes_association_scope");
  });

  it.each(["missing", "invalid"] as const)(
    "does not turn %s window traffic into zero",
    (quality) => {
      const html = render(ConsoleNodeTable, {
        props: {
          nodes: [{ ...reported, window_traffic_quality: quality, window_traffic_bytes: null }],
          traffic: consoleNodeTrafficFixture,
          at,
        },
      }).body;
      expect(windowCell(html)).toContain(`console_nodes_window_${quality}`);
      expect(windowCell(html)).not.toContain("0 B");
    }
  );

  it.each([null, undefined, "unavailable", "unconfigured"] as const)(
    "never shows reported values without usable source metadata (%s)",
    (availability) => {
      const traffic =
        availability == null ? availability : { ...consoleNodeTrafficFixture, availability };
      expect(nodeWindowTrafficQuality(reported, traffic)).toBe("missing");
      const html = render(ConsoleNodeTable, {
        props: { nodes: [reported], traffic: traffic ?? null, at },
      }).body;
      expect(windowCell(html)).toContain("console_nodes_window_missing");
      expect(windowCell(html)).not.toContain("0 B");
    }
  );

  it.each([-1, 1.5, Number.NaN, Number.POSITIVE_INFINITY, 2 ** 53])(
    "rejects a malformed numeric total %s",
    (total) => {
      expect(
        nodeWindowTrafficQuality(
          { ...reported, window_traffic_bytes: total },
          consoleNodeTrafficFixture
        )
      ).toBe("invalid");
    }
  );

  it("marks retained range values stale while preserving both read times", () => {
    const traffic: ConsoleNodeTraffic = {
      ...consoleNodeTrafficFixture,
      availability: "stale",
      error: "request_failed",
      attempted_at: "2026-10-24T09:00:00Z",
    };
    const html = render(NodeTrafficWindow, {
      props: { value: "today", traffic, at, onChange: () => {} },
    }).body;
    expect(html).toContain("console_nodes_availability_stale");
    expect(html).toContain("console_nodes_window_request_failed");
    expect(html).toContain("2026-10-24 08:01:00.000 UTC");
    expect(html).toContain("2026-10-24 09:00:00.000 UTC");
    const cell = windowCell(
      render(ConsoleNodeTable, { props: { nodes: [reported], traffic, at } }).body
    );
    expect(cell).toContain("0 B");
    expect(cell).toContain("console_nodes_availability_stale");
  });

  it.each(["available", "partial", "stale", "unavailable", "unconfigured"] as const)(
    "discloses %s coverage, exact UTC boundaries and unknown sampling completeness",
    (availability) => {
      const html = render(NodeTrafficWindow, {
        props: {
          value: "today",
          traffic: { ...consoleNodeTrafficFixture, availability, inventory_nodes: null },
          at,
          onChange: () => {},
        },
      }).body;
      expect(html).toContain(`console_nodes_availability_${availability}`);
      expect(html).toContain("2026-10-24 00:00:00.000 UTC");
      expect(html).toContain("2026-10-24 23:59:59.999 UTC");
      expect(html).toContain("console_nodes_window_coverage[matched=1;total=console_unknown]");
      expect(html).toContain("console_nodes_window_source");
      expect(html).toContain("console_nodes_window_history");
    }
  );

  it.each(["request_failed", "invalid_response", "not_configured"] as const)(
    "renders the safe source failure reason %s",
    (error) => {
      const html = render(NodeTrafficWindow, {
        props: {
          value: "today",
          traffic: { ...consoleNodeTrafficFixture, error },
          at,
          onChange: () => {},
        },
      }).body;
      expect(html).toContain(`console_nodes_window_${error}`);
    }
  );

  it("keeps UTC explicit independent of the browser's display timezone", () => {
    expect(nodeTrafficDate("2026-10-24T08:00:00+08:00", at)).toBe("2026-10-24 00:00:00.000 UTC");
    expect(nodeTrafficDate(null, at)).toBe("console_unknown");
    expect(nodeTrafficDate("bad-date", at)).toBe("console_unknown");
  });

  it.each(["en", "ru", "zh-hans"])(
    "renders the real localized selector and evidence in %s",
    (language) => {
      const locale: Record<string, string> = JSON.parse(
        readFileSync(new URL(`../../../../locales/${language}.json`, import.meta.url), "utf8")
      );
      const translated: ConsoleNodesTranslate = (key, params) => {
        let message = locale[`admin_${key}`];
        expect(message, key).toBeTruthy();
        for (const [name, value] of Object.entries(params ?? {}))
          message = message.replaceAll(`{${name}}`, String(value));
        return message;
      };
      for (const value of ["today", "7d", "30d"] as const) {
        const html = render(NodeTrafficWindow, {
          props: { value, traffic: consoleNodeTrafficFixture, at: translated, onChange: () => {} },
        }).body;
        expect(html).toContain(locale[`admin_console_nodes_window_${value}`]);
        expect(html).toContain("admin-select-wrap");
        expect(html).not.toContain("{start}");
        expect(html).not.toContain("{matched}");
      }
    }
  );
});
