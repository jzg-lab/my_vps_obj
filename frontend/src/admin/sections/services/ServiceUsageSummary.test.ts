import { readFileSync } from "node:fs";
import { render } from "svelte/server";
import { describe, expect, it } from "vitest";
import ServiceUsageSummary from "./ServiceUsageSummary.svelte";
import { consoleNodeServiceFixture } from "$lib/admin/consoleNodesFixtures";

const service = {
  ...consoleNodeServiceFixture.service,
  traffic_rule: "total" as const,
  last_usage_sync_at: null,
  usage_error: null,
};
const at = (key: string) => key;
describe("service usage summary", () => {
  it("does not label never-observed usage as failed or show a monthly reset for total plans", () => {
    const html = render(ServiceUsageSummary, { props: { service, at } }).body;
    expect(html).toContain("services_usage_missing");
    expect(html).not.toContain("services_usage_unconfirmed");
    expect(html).not.toContain("services_usage_stale");
    expect(html).not.toContain("services_next_reset");
  });
  it("shows a first-read failure once without claiming an earlier confirmed value", () => {
    const html = render(ServiceUsageSummary, {
      props: { service: { ...service, usage_error: "panel_usage_unavailable" }, at },
    }).body;
    expect(html).toContain("services_usage_unconfirmed");
    expect(html).not.toContain("services_usage_stale");
  });
  it("shows retained zero usage with its observation time after a failed read", () => {
    const html = render(ServiceUsageSummary, {
      props: {
        service: {
          ...service,
          used_bytes: 0,
          last_usage_sync_at: "2026-10-27T00:00:00Z",
          usage_error: "panel_usage_unavailable",
        },
        at,
      },
    }).body;
    expect(html).toContain("0 B /");
    expect(html).toContain("2026-10-27 08:00");
    expect(html).toContain("services_usage_stale");
  });
  it.each(["en", "ru", "zh-hans"])("has localized missing-data explanations in %s", (language) => {
    const locale = JSON.parse(
      readFileSync(new URL(`../../../../../locales/${language}.json`, import.meta.url), "utf8")
    );
    for (const key of [
      "account_access_scope",
      "console_nodes_pending_configuration",
      "console_nodes_resources_unconfigured",
      "console_visual_history_unconfigured",
      "console_visual_history_failed",
      "console_visual_history_no_samples",
    ])
      expect(locale[`admin_${key}`]).toBeTruthy();
  });
});
