import { render } from "svelte/server";
import { describe, expect, it } from "vitest";
import ConsoleOverviewSignals from "../../admin/sections/overview/ConsoleOverviewSignals.svelte";
import ConsoleNodeTrafficChart from "../../admin/sections/nodes/ConsoleNodeTrafficChart.svelte";
import {
  consoleNodeFixture,
  consoleNodeDetailFixture,
  consoleNodeTrafficFixture,
} from "./consoleNodesFixtures";
import type { ConsoleNodesPage } from "./consoleNodesTypes";

const at = (key: string) => key;
const inventory: ConsoleNodesPage = {
  nodes: [consoleNodeFixture],
  total: 10,
  page: 0,
  page_size: 5,
  coverage: "partial",
  sources: consoleNodeDetailFixture.sources,
  traffic: consoleNodeTrafficFixture,
  cache_ttl_seconds: 15,
};
describe("overview data boundaries", () => {
  it.each(["unavailable", "partial", "stale"] as const)(
    "does not turn empty %s inventory into a healthy zero",
    (coverage) => {
      const html = render(ConsoleOverviewSignals, {
        props: {
          nodes: { ...inventory, nodes: [], coverage },
          stale: false,
          stats: null,
          at,
          onNodes: () => {},
          onFeedback: () => {},
        },
      }).body;
      expect(html).not.toContain("0 / 0");
      expect(html).toContain("console_unknown");
    }
  );
  it("reports verified empty inventory as zero and stale status as unknown", () => {
    const props = {
      nodes: { ...inventory, nodes: [], coverage: "complete" as const },
      stale: false,
      stats: null,
      at,
      onNodes: () => {},
      onFeedback: () => {},
    };
    expect(render(ConsoleOverviewSignals, { props }).body).toContain("0 / 0");
    expect(
      render(ConsoleOverviewSignals, { props: { ...props, nodes: inventory, stale: true } }).body
    ).toContain("console_unknown / 1");
  });
  it("distinguishes reported zero from missing traffic without inventing historical series", () => {
    const html = render(ConsoleNodeTrafficChart, {
      props: {
        nodes: {
          ...inventory,
          nodes: [
            { ...consoleNodeFixture, window_traffic_bytes: 0, window_traffic_quality: "reported" },
            { ...consoleNodeFixture, id: "missing" },
          ],
        },
        comparison: true,
        stale: false,
        at,
        onNode: () => {},
      },
    }).body;
    expect(html).toContain("0 B");
    expect(html).toContain("console_nodes_window_missing");
    expect(html).toContain("console_node_daily_scope");
    expect(html).not.toContain("NaN");
    expect(html).not.toContain("Infinity");
  });
  it.each(["stale", "unavailable"] as const)(
    "does not count an unreadable %s node source as zero online",
    (availability) => {
      const html = render(ConsoleOverviewSignals, {
        props: {
          nodes: {
            ...inventory,
            sources: inventory.sources.map((source) =>
              source.source === "nodes" ? { ...source, availability } : source
            ),
          },
          stale: false,
          stats: null,
          at,
          onNodes: () => {},
          onFeedback: () => {},
        },
      }).body;
      expect(html).toContain("console_unknown / 1");
    }
  );
});
