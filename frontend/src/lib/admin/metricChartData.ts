import type uPlot from "uplot";

export type MetricSeries = { label: string; values: (number | null)[] };

export function metricChartData(labels: string[], series: MetricSeries[]): uPlot.AlignedData {
  return [
    labels.map((_, index) => index),
    ...series.map((row) =>
      labels.map((_, index) => {
        const value = row.values[index];
        return typeof value === "number" && Number.isFinite(value) && value >= 0 ? value : null;
      })
    ),
  ];
}
