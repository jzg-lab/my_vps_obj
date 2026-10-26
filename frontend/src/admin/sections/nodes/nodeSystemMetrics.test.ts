import { render } from "svelte/server";
import { describe, expect, it } from "vitest";
import type { ConsoleNodesTranslate } from "$lib/admin/consoleNodesTypes";
import NodeSystemMetrics from "./NodeSystemMetrics.svelte";
import {
  nodeControlStatus,
  nodeMetricQuality,
  nodeMetricRows,
  nodeMetricText,
  bytesPerSecondToMbps,
  nodeSpeedSummary,
  type MetricsNode,
  type MetricsSource,
  type NodeMetricField,
  type NodeSystemMetrics as SystemMetrics,
} from "./nodeSystemMetrics";

const at: ConsoleNodesTranslate = (key, params) =>
  params ? `${key}[${Object.values(params).join(",")}]` : key;

const metrics: SystemMetrics = {
  cpu_cores: 4,
  cpu_model: "Example CPU",
  memory_total_bytes: 4096,
  memory_free_bytes: 4096,
  memory_used_bytes: 0,
  load_1m: 0,
  load_5m: 0.5,
  load_15m: 1.25,
  uptime_seconds: 0,
  interface_name: "eth0",
  rx_bytes_per_second: 0,
  tx_bytes_per_second: 512.5,
  rx_total_bytes: 0,
  tx_total_bytes: 1024,
  sampled_at: null,
  invalid_fields: [],
};

const node: MetricsNode = {
  id: "10000000-0000-0000-0000-000000000001",
  name: "Node visible system",
  address: "192.0.2.1",
  country_code: null,
  status: "online",
  is_disabled: false,
  is_connecting: false,
  last_status_change_at: "2026-10-23T01:00:00Z",
  observed_at: "2026-10-24T01:00:00Z",
  observation_basis: "panel_read_time_sample_time_unavailable",
  profile_id: null,
  inbound_ids: [],
  groups: [],
  users_online: 0,
  users_online_quality: "reported",
  system: metrics,
  online_scope: "panel_reported_identities_not_unique_customers",
  traffic_used_bytes: null,
  traffic_tracking_enabled: null,
  traffic_reset_day: null,
  traffic_scope: "panel_node_tracking_period_not_service_billing",
  traffic_unit: "bytes",
  traffic_window: "panel_tracking_counter_boundaries_unavailable",
  window_traffic_bytes: null,
  window_traffic_quality: "missing",
};

const source: MetricsSource = {
  source: "nodes",
  availability: "available",
  attempted_at: "2026-10-24T01:00:00Z",
  last_success_at: "2026-10-24T01:00:00Z",
  error: null,
};

function rowHtml(html: string, field: NodeMetricField) {
  const row = html.match(new RegExp(`<tr[^>]*data-node-metric="${field}"[\\s\\S]*?</tr>`));
  expect(row, field).not.toBeNull();
  return row![0];
}

describe("node system metric values", () => {
  it("converts byte rates to decimal Mbps and summarizes observed RX/TX peaks separately", () => {
    const samples = [
      {
        sampled_at: "2026-10-26T08:00:00Z",
        rx_bytes_per_second: 1_000_000,
        tx_bytes_per_second: 500_000,
      },
      {
        sampled_at: "2026-10-26T08:10:00Z",
        rx_bytes_per_second: 2_000_000,
        tx_bytes_per_second: 3_000_000,
      },
      {
        sampled_at: "2026-10-26T08:20:00Z",
        rx_bytes_per_second: null,
        tx_bytes_per_second: 1_000_000,
      },
    ];
    const summary = nodeSpeedSummary(samples);
    expect(bytesPerSecondToMbps(2_000_000)).toBe(16);
    expect(bytesPerSecondToMbps(-1)).toBeNull();
    expect(summary.latest).toBe(samples[2]);
    expect(summary.rxPeakBytesPerSecond).toBe(2_000_000);
    expect(summary.txPeakBytesPerSecond).toBe(3_000_000);
  });

  it("labels historical speed with the latest sample and peak in Mbps", () => {
    const html = render(NodeSystemMetrics, {
      props: {
        node: {
          ...node,
          speed_history: [
            {
              sampled_at: "2026-10-26T08:00:00Z",
              rx_bytes_per_second: 1_000_000,
              tx_bytes_per_second: 500_000,
            },
            {
              sampled_at: "2026-10-26T08:10:00Z",
              rx_bytes_per_second: 2_000_000,
              tx_bytes_per_second: 3_000_000,
            },
          ],
        },
        source,
        at,
      },
    }).body;
    expect(html).toContain("data-speed-summary");
    expect(html).toContain("console_node_speed_latest");
    expect(html).toContain("console_node_speed_peak");
    expect(html).toContain("16 Mbps");
    expect(html).toContain("24 Mbps");
    expect(html).toContain("RX 16 Mbps · TX 24 Mbps");
    expect(html).toContain("2026-10-26 16:10");
  });

  it("shows daily traffic before technical rows and keeps missing days distinct from zero", () => {
    const html = render(NodeSystemMetrics, {
      props: {
        node: {
          ...node,
          daily_traffic: [
            { date: "2026-10-23", bytes: 0 },
            { date: "2026-10-24", bytes: null },
          ],
        },
        source,
        at,
      },
    }).body;
    expect(html).toContain("console_node_daily_traffic");
    expect(html).toContain("console_node_daily_scope");
    expect(html).toContain("console_nodes_window_traffic: console_unknown");
    expect(html.indexOf("data-node-daily-traffic")).toBeLessThan(html.indexOf("data-node-metric="));
    expect(html).toContain("10-23");
    expect(html).toContain("10-24");
    expect(html).toContain("console_visual_history_missing");
  });

  it("preserves known zeros and displays the actual units", () => {
    const html = render(NodeSystemMetrics, { props: { node, source, at } }).body;
    expect((html.match(/data-node-metric=/g) ?? []).length).toBe(14);
    expect(rowHtml(html, "memory_used_bytes")).toContain("0 B");
    expect(rowHtml(html, "rx_bytes_per_second")).toContain("console_node_metrics_rate_value[0 B]");
    expect(rowHtml(html, "tx_bytes_per_second")).toContain(
      "console_node_metrics_rate_value[512.5 B]"
    );
    expect(rowHtml(html, "tx_total_bytes")).toContain("1 KiB");
    expect(rowHtml(html, "uptime_seconds")).toContain("console_node_metrics_seconds_value[0]");
    expect(rowHtml(html, "load_5m")).toMatch(/>0.5</);
    expect(rowHtml(html, "load_5m")).not.toContain("%");
    expect(html).toContain("console_node_metrics_load_scope");
    expect(html).toContain("console_node_metrics_network_scope");
  });

  it("keeps provided zero, missing and invalid fields visibly distinct", () => {
    const system: SystemMetrics = {
      ...metrics,
      memory_free_bytes: null,
      memory_total_bytes: null,
      invalid_fields: ["memory_total_bytes"],
    };
    const html = render(NodeSystemMetrics, {
      props: { node: { ...node, system }, source, at },
    }).body;
    expect(rowHtml(html, "memory_used_bytes")).toContain('data-metric-quality="reported"');
    expect(rowHtml(html, "memory_free_bytes")).toContain('data-metric-quality="missing"');
    expect(rowHtml(html, "memory_free_bytes")).toContain("console_node_metrics_missing");
    expect(rowHtml(html, "memory_total_bytes")).toContain('data-metric-quality="invalid"');
    expect(rowHtml(html, "memory_total_bytes")).toContain("console_node_metrics_invalid");
    expect(rowHtml(html, "memory_total_bytes")).not.toContain("0 B");
  });

  it("handles older responses without a system block without inventing values", () => {
    const html = render(NodeSystemMetrics, {
      props: { node: { ...node, system: undefined }, source, at },
    }).body;
    expect((html.match(/data-metric-quality="missing"/g) ?? []).length).toBe(14);
    expect(html).not.toContain("0 B");
  });

  it.each([Number.NaN, Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY, -1])(
    "does not render a malformed numeric value (%s)",
    (bad) => {
      const system = { ...metrics, memory_used_bytes: bad };
      const row = nodeMetricRows.find((item) => item.field === "memory_used_bytes")!;
      expect(nodeMetricQuality(system, row.field)).toBe("invalid");
      expect(nodeMetricText(system, row, at)).toBe("console_node_metrics_invalid");
    }
  );

  it("does not reinterpret hardware cores as a CPU percentage", () => {
    for (const bad of [0, 0.5, 2 ** 53])
      expect(nodeMetricQuality({ ...metrics, cpu_cores: bad }, "cpu_cores")).toBe("invalid");
    expect(nodeMetricQuality({ ...metrics, cpu_model: " " }, "cpu_model")).toBe("invalid");
    expect(nodeMetricQuality({ ...metrics, interface_name: "" }, "interface_name")).toBe("invalid");
    const row = nodeMetricRows.find((item) => item.field === "load_1m")!;
    expect(nodeMetricText({ ...metrics, load_1m: 4.5 }, row, at)).toBe("4.5");
  });

  it("does not round a tiny positive rate into a displayed zero", () => {
    const row = nodeMetricRows.find((item) => item.field === "rx_bytes_per_second")!;
    expect(nodeMetricText({ ...metrics, rx_bytes_per_second: 0.001 }, row, at)).toBe(
      "console_node_metrics_rate_value[0.001 B]"
    );
  });

  it("escapes upstream hardware names instead of rendering markup", () => {
    const html = render(NodeSystemMetrics, {
      props: {
        node: { ...node, system: { ...metrics, cpu_model: "<script>alert(1)</script>" } },
        source,
        at,
      },
    }).body;
    expect(html).not.toContain("<script>alert(1)</script>");
    expect(html).toContain("&lt;script>");
  });
});

describe("observation quality and management boundaries", () => {
  it.each(["available", "partial", "stale", "unavailable", "unsupported", "unconfigured"] as const)(
    "separates %s source state from the unknown sample time",
    (availability) => {
      const html = render(NodeSystemMetrics, {
        props: { node, source: { ...source, availability }, at },
      }).body;
      expect(html).toContain(`console_nodes_availability_${availability}`);
      expect(html).toContain('role="status"');
      const readTime = html.match(/<p[^>]*data-metrics-read-time[\s\S]*?<\/p>/)?.[0];
      const sampleTime = html.match(/<p[^>]*data-metrics-sample-time[\s\S]*?<\/p>/)?.[0];
      expect(readTime).toContain("2026-10-24 09:00");
      expect(sampleTime).toContain("console_node_metrics_sample_unknown");
      expect(sampleTime).not.toContain("2026-10");
      expect(html).toContain("console_node_metrics_freshness");
      expect(rowHtml(html, "memory_used_bytes")).toContain("0 B");
    }
  );

  it("shows a failed attempt while retaining the earlier successful read time", () => {
    const html = render(NodeSystemMetrics, {
      props: {
        node,
        source: {
          ...source,
          availability: "stale",
          error: "request_failed",
          attempted_at: "2026-10-24T02:00:00Z",
        },
        at,
      },
    }).body;
    expect(html).toContain("console_node_metrics_error_request_failed");
    expect(html).toContain("2026-10-24 09:00");
    expect(html).toContain("2026-10-24 10:00");
    expect(html).toContain("console_nodes_status_unknown");
    expect(html).not.toContain("console_nodes_status_online");
  });

  it("keeps missing source metadata unknown and ignores unrelated sources", () => {
    for (const current of [undefined, { ...source, source: "hosts" as const }]) {
      const html = render(NodeSystemMetrics, { props: { node, source: current, at } }).body;
      expect(html).not.toContain("console_nodes_availability_available");
      expect(html).toContain("console_nodes_status_unknown");
      expect(html).toContain("console_node_metrics_sample_unknown");
    }
  });

  it.each(["request_failed", "invalid_response", "not_supported", "not_configured"] as const)(
    "exposes the source error reason %s without raw responses",
    (error) => {
      const html = render(NodeSystemMetrics, {
        props: { node, source: { ...source, error }, at },
      }).body;
      expect(html).toContain(`console_node_metrics_error_${error}`);
    }
  );

  it("explains the cache-default online zero instead of displaying it as measured", () => {
    const html = render(NodeSystemMetrics, {
      props: {
        node: {
          ...node,
          users_online: null,
          users_online_quality: "unverified_zero",
          system: undefined,
        },
        source,
        at,
      },
    }).body;
    expect(html).toContain("console_node_metrics_online_unverified");
    expect(html).not.toContain("0 B");
    expect(html).not.toContain("Measured zero");
  });

  it("does not invent proxy latency or loss from an online management status", () => {
    const html = render(NodeSystemMetrics, { props: { node, source, at } }).body;
    expect(nodeControlStatus(node, source)).toBe("online");
    expect(html).toContain("console_nodes_status_online");
    expect(html).toContain("console_node_metrics_control_scope");
    expect(html).toContain("console_node_metrics_probe_missing");
    expect((html.match(/console_node_metrics_not_collected/g) ?? []).length).toBe(2);
    expect(html).not.toContain("0 ms");
    const connectivity = html.slice(html.indexOf('aria-label="console_node_metrics_connectivity"'));
    expect(connectivity).not.toContain("0%");
    expect(html).not.toContain("<button");
  });

  it("shows disabled and connecting flags as management state, not a proxy probe", () => {
    const html = render(NodeSystemMetrics, {
      props: {
        node: { ...node, status: "offline", is_disabled: true, is_connecting: true },
        source,
        at,
      },
    }).body;
    expect(html).toContain("console_node_metrics_control_status");
    expect(html).toContain("console_nodes_disabled");
    expect(html).toContain("console_nodes_connecting");
    expect(html).toContain("console_nodes_status_offline");
    expect((html.match(/console_node_metrics_not_collected/g) ?? []).length).toBe(2);
  });
});
