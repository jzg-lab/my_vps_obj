import { render } from "svelte/server";
import { describe, expect, it } from "vitest";
import { replacementFixture } from "$lib/admin/exitReplacementFixtures";
import ExitReplacementImpact from "./ExitReplacementImpact.svelte";
import ExitReplacementStatus from "./ExitReplacementStatus.svelte";

const at = (key: string) => key;
const currentUrl = "https://console.example/app/admin/services?theme_preview=dark&service_id=old";
const routePrefix = "/app";

describe("replacement impact identities", () => {
  it.each(["draft", "confirmation"])("shows real identities during %s", (stage) => {
    const { state, draft, affected } = replacementFixture();
    if (stage === "draft") {
      state.replacement = null;
      state.draft = draft;
    }
    const html = render(ExitReplacementStatus, {
      props: { at, data: state, currentUrl, routePrefix },
    }).body;
    expect(html).toContain('aria-label="replacement_impact_entities"');
    expect(html).toContain(affected.service.name);
    expect(html).toContain(affected.service.id);
    expect(html).toContain(String(affected.service.user_id));
    expect(html).toContain("console_resource_scope");
    expect(html).toMatch(/href="https:\/\/console.example\/app\/admin\/users\/910003\?/);
    expect(html).toMatch(
      /href="https:\/\/console.example\/app\/admin\/services\?[^"]*service_id=f{32}"/
    );
    expect(html.match(/target="_blank"/g)).toHaveLength(3);
    expect(html.match(/rel="noopener noreferrer"/g)).toHaveLength(3);
  });

  it("keeps a stable service ID when its name and customer are unavailable", () => {
    const impact = replacementFixture().draft.impacts![1];
    const html = render(ExitReplacementImpact, {
      props: { at, impacts: [impact], currentUrl, routePrefix },
    }).body;
    expect(html).toContain(impact.service_id);
    expect(html).toContain("replacement_service_unnamed");
    expect(html).toContain("replacement_customer_unknown");
    expect(html).not.toContain("/admin/users/");
    expect(html.match(/target="_blank"/g)).toHaveLength(1);
  });

  it("renders external and missing ownership without invented identity links", () => {
    const impact = replacementFixture().draft.impacts![2];
    Reflect.deleteProperty(impact, "customer_id");
    const html = render(ExitReplacementImpact, {
      props: { at, impacts: [impact], currentUrl, routePrefix },
    }).body;
    expect(html).toContain("replacement_service_external");
    expect(html).toContain("replacement_customer_unknown");
    expect(html).toContain("console_resource_reload");
    expect(html).not.toContain("href=");
    expect(html).not.toContain("undefined");
    expect(html).not.toContain("null");
  });

  it("escapes supplied service names and renders an empty scope explicitly", () => {
    const impact = replacementFixture().draft.impacts![0];
    impact.service_name = '<img src=x onerror="private">';
    const html = render(ExitReplacementImpact, { props: { at, impacts: [impact] } }).body;
    expect(html).toContain("&lt;img");
    expect(html).not.toContain("<img");
    expect(render(ExitReplacementImpact, { props: { at, impacts: [] } }).body).toContain(
      "console_resource_no_services"
    );
  });
});
