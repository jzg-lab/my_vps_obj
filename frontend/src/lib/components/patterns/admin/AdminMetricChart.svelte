<script lang="ts">
  import uPlot from "uplot";
  import "uplot/dist/uPlot.min.css";
  import { metricChartData, type MetricSeries } from "$lib/admin/metricChartData";
  import AdminChartEmptyState from "./AdminChartEmptyState.svelte";
  import AdminTable from "./AdminTable.svelte";

  let {
    labels,
    series,
    title,
    missingLabel,
    tableLabel,
    timeLabel,
    format = String,
    variant = "line",
    height = 240,
  }: {
    labels: string[];
    series: MetricSeries[];
    title: string;
    missingLabel: string;
    tableLabel: string;
    timeLabel: string;
    format?: (value: number) => string;
    variant?: "line" | "bar";
    height?: number;
  } = $props();

  let host = $state<HTMLDivElement | undefined>();
  const data = $derived(metricChartData(labels, series));
  const hasSamples = $derived(
    data.slice(1).some((values) => values.some((value) => value !== null))
  );
  const seriesColors = ["var(--accent)", "var(--info)", "var(--warning)"];

  $effect(() => {
    if (!host || !hasSamples) return;
    const element = host;
    const style = getComputedStyle(element);
    const color = (name: string, fallback: string) =>
      style.getPropertyValue(name).trim() || fallback;
    const colors = [
      color("--accent", "#22c55e"),
      color("--info", "#60a5fa"),
      color("--warning", "#fbbf24"),
    ];
    const muted = color("--admin-muted", "#94a3b8");
    const border = color("--admin-border", "#334155");
    const plot = new uPlot(
      {
        width: Math.max(160, element.clientWidth),
        height,
        legend: { show: false },
        cursor: { drag: { x: false, y: false } },
        scales: {
          x: { time: false, range: [-0.5, Math.max(0.5, labels.length - 0.5)] },
          y: { range: [0, null] },
        },
        series: [
          {},
          ...series.map((row, index) => ({
            label: row.label,
            stroke: colors[index % colors.length],
            fill: variant === "bar" ? colors[index % colors.length] : undefined,
            width: 2,
            spanGaps: false,
            points: { show: variant === "line", size: 5 },
            paths:
              variant === "bar"
                ? uPlot.paths.bars?.({
                    size: [0.65, 32],
                    radius: 0.08,
                    ...(series.length > 1
                      ? {
                          disp: {
                            x0: {
                              unit: 1,
                              values: () =>
                                labels.map((_, day) => day - 0.35 + (index * 0.7) / series.length),
                            },
                            size: { unit: 1, values: () => labels.map(() => 0.7 / series.length) },
                          },
                        }
                      : {}),
                  })
                : undefined,
          })),
        ],
        axes: [
          {
            stroke: muted,
            grid: { show: false },
            ticks: { stroke: border },
            splits: (plot) => {
              const maxTicks = Math.max(2, Math.min(7, Math.floor((plot.width - 72) / 64)));
              return labels
                .map((_, index) => index)
                .filter((index) => index % Math.max(1, Math.ceil(labels.length / maxTicks)) === 0);
            },
            values: (_plot, ticks) => ticks.map((value) => labels[value] ?? ""),
            font: "11px system-ui",
          },
          {
            stroke: muted,
            grid: { stroke: border },
            ticks: { stroke: border },
            size: 72,
            values: (_plot, ticks) => ticks.map(format),
            font: "10px system-ui",
          },
        ],
      },
      data,
      element
    );
    const resize = new ResizeObserver(() => {
      if (element.clientWidth > 0) plot.setSize({ width: element.clientWidth, height });
    });
    resize.observe(element);
    return () => {
      resize.disconnect();
      plot.destroy();
    };
  });
</script>

<section class="metric-chart" aria-label={title}>
  {#if hasSamples}
    <div bind:this={host} class="plot" aria-hidden="true"></div>
    <div class="series-labels">
      {#each series as row, index}<span>
          <i aria-hidden="true" style={`background:${seriesColors[index % seriesColors.length]}`}
          ></i>{row.label}
        </span>{/each}
    </div>
  {:else}
    <AdminChartEmptyState label={missingLabel} plotHeight={height} />
  {/if}
  <details>
    <summary>{tableLabel}</summary>
    <AdminTable>
      <thead
        ><tr
          ><th>{timeLabel}</th>{#each series as row}<th>{row.label}</th>{/each}</tr
        ></thead
      >
      <tbody>
        {#each labels as label, index}
          <tr
            ><td data-label={timeLabel}>{label}</td>{#each series as row, seriesIndex}
              {@const value = data[seriesIndex + 1]?.[index]}
              <td data-label={row.label}
                >{typeof value === "number" ? format(value) : missingLabel}</td
              >
            {/each}</tr
          >
        {/each}
      </tbody>
    </AdminTable>
  </details>
</section>

<style>
  .metric-chart,
  .plot {
    min-width: 0;
    width: 100%;
  }
  .plot {
    overflow: hidden;
  }
  .series-labels,
  summary {
    color: var(--admin-muted);
    font-size: 12px;
    overflow-wrap: anywhere;
  }
  .series-labels {
    display: flex;
    flex-wrap: wrap;
    gap: 8px 16px;
  }
  .series-labels span {
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }
  .series-labels i {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex: 0 0 auto;
  }
  summary {
    cursor: pointer;
    padding-block: 8px;
  }
</style>
