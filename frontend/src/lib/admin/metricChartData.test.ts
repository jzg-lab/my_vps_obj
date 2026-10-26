import { describe, expect, it } from "vitest";
import { metricChartData } from "./metricChartData";

describe("metric chart observations", () => {
  it("preserves zero and fractional rates while leaving missing or invalid samples as gaps", () => {
    expect(
      metricChartData(
        ["a", "b", "c", "d", "e", "f", "g"],
        [{ label: "RX", values: [0, 0.25, null, -1, Infinity, NaN] }]
      )
    ).toEqual([
      [0, 1, 2, 3, 4, 5, 6],
      [0, 0.25, null, null, null, null, null],
    ]);
  });

  it("aligns every series to the displayed labels and drops out-of-window observations", () => {
    expect(
      metricChartData(
        ["today"],
        [
          { label: "first", values: [12, 99] },
          { label: "second", values: [] },
        ]
      )
    ).toEqual([[0], [12], [null]]);
  });
});
