import type { components } from "$lib/api/openapi.generated";
import type { ConsoleNodesTranslate } from "$lib/admin/consoleNodesTypes";
import { serviceBytes } from "$lib/admin/servicePlans";

export type NodeSystemMetrics = components["schemas"]["ConsoleNodeSystemOut"];
export type NodeMetricField = components["schemas"]["ConsoleNodeSystemField"];
export type MetricsNode = components["schemas"]["ConsoleNodeOut"];
export type MetricsSource = components["schemas"]["ConsoleNodeSourceOut"];
export type NodeSpeedSample = components["schemas"]["ConsoleSpeedSampleOut"];
type MetricFormat = "number" | "text" | "bytes" | "rate" | "seconds";

export const nodeMetricRows = [
  { field: "cpu_cores", format: "number" },
  { field: "cpu_model", format: "text" },
  { field: "memory_total_bytes", format: "bytes" },
  { field: "memory_free_bytes", format: "bytes" },
  { field: "memory_used_bytes", format: "bytes" },
  { field: "load_1m", format: "number" },
  { field: "load_5m", format: "number" },
  { field: "load_15m", format: "number" },
  { field: "uptime_seconds", format: "seconds" },
  { field: "interface_name", format: "text" },
  { field: "rx_bytes_per_second", format: "rate" },
  { field: "tx_bytes_per_second", format: "rate" },
  { field: "rx_total_bytes", format: "bytes" },
  { field: "tx_total_bytes", format: "bytes" },
] as const satisfies readonly { field: NodeMetricField; format: MetricFormat }[];

export function nodeMetricQuality(
  metrics: NodeSystemMetrics | undefined,
  field: NodeMetricField
): "reported" | "missing" | "invalid" {
  if (metrics?.invalid_fields?.includes(field)) return "invalid";
  const value = metrics?.[field];
  if (value === null || value === undefined) return "missing";
  if (field === "cpu_model" || field === "interface_name")
    return typeof value === "string" && value.trim() ? "reported" : "invalid";
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) return "invalid";
  if (field === "cpu_cores" && (!Number.isSafeInteger(value) || value === 0)) return "invalid";
  return "reported";
}

export function nodeMetricText(
  metrics: NodeSystemMetrics | undefined,
  row: (typeof nodeMetricRows)[number],
  at: ConsoleNodesTranslate
): string {
  const quality = nodeMetricQuality(metrics, row.field);
  if (quality !== "reported") return at(`console_node_metrics_${quality}`);
  const value = metrics?.[row.field];
  if (typeof value !== "number") return String(value);
  if (row.format === "bytes" || row.format === "rate") {
    // Keep a tiny positive rate from being rounded into a displayed zero.
    const formatted = value > 0 && value < 0.005 ? `${value} B` : serviceBytes(value);
    return row.format === "rate"
      ? at("console_node_metrics_rate_value", { value: formatted })
      : formatted;
  }
  if (row.format === "seconds") return at("console_node_metrics_seconds_value", { value });
  return String(value);
}

export function nodeControlStatus(node: MetricsNode, source: MetricsSource | undefined) {
  return source?.source === "nodes" &&
    (source.availability === "available" || source.availability === "partial")
    ? node.status
    : "unknown";
}

export function nodeSpeedSummary(samples: NodeSpeedSample[]) {
  const latest = samples.at(-1);
  const rxRates = samples.map((sample) => sample.rx_bytes_per_second).filter(validRate);
  const txRates = samples.map((sample) => sample.tx_bytes_per_second).filter(validRate);
  return {
    latest,
    rxPeakBytesPerSecond: rxRates.length ? Math.max(...rxRates) : null,
    txPeakBytesPerSecond: txRates.length ? Math.max(...txRates) : null,
  };
}

function validRate(value: number | null | undefined): value is number {
  return typeof value === "number" && Number.isFinite(value) && value >= 0;
}

export function bytesPerSecondToMbps(value: number | null): number | null {
  return typeof value === "number" && Number.isFinite(value) && value >= 0
    ? (value * 8) / 1_000_000
    : null;
}
