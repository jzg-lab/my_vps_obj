import { describe, expect, it } from "vitest";
import { createApiClient, unwrap } from "../publicApi";
import { consoleNodeFixture } from "$lib/admin/consoleNodesFixtures";
import type { components } from "$lib/api/openapi.generated";
import {
  consoleResourcePreviewDemoResponse,
  consoleResourcePreviewFixture,
  consoleResourceCatalogFixture,
  consoleResourceDraftPreviewFixture,
} from "./consoleResourcePreview";
import { initialDraft } from "../../../admin/sections/nodes/resourceDraftPreview";

const change: components["schemas"]["ResourceNodeChange"] = {
  operation: "node_disable",
  target_id: consoleNodeFixture.id,
  force_restart: false,
};
const client = createApiClient({ mockApi: consoleResourcePreviewDemoResponse });
describe("read-only resource preview mock", () => {
  it("provides a fresh safe catalog without mutating shared inventory", async () => {
    const result = unwrap(await client.api("/admin/console/resources/catalog"));
    expect(result).toMatchObject({
      draft_available: true,
      execution_available: false,
      coverage: "complete",
    });
    expect(result.profiles[0].inbounds).toHaveLength(2);
    result.groups[0].inbound_ids.length = 0;
    expect(consoleResourceCatalogFixture().groups[0].inbound_ids).toHaveLength(1);
    expect(JSON.stringify(result)).not.toMatch(/privateKey|raw_config|credential/);
    expect(
      consoleResourcePreviewDemoResponse("/admin/console/resources/catalog", { method: "POST" })
    ).toEqual({ ok: false, error: "method_not_allowed" });
  });

  it.each(["group", "host"] as const)(
    "previews and revalidates a %s draft without inventory changes",
    async (kind) => {
      const catalog = consoleResourceCatalogFixture();
      const target = { kind, id: (kind === "group" ? catalog.groups : catalog.hosts)[0].id };
      const draft = initialDraft(catalog, target)!;
      if (draft.operation === "group_inbounds") draft.inbound_ids = [];
      else
        draft.patch = {
          ...draft.patch,
          is_hidden: true,
          group_mode: "ALLOW_ONLY",
          group_ids: [catalog.groups[1].id],
        };
      const preview = unwrap(
        await client.api("/admin/console/resources/preview", {
          method: "POST",
          body: JSON.stringify({ change: draft }),
        })
      );
      expect(preview).toMatchObject({
        execution_available: false,
        coverage: "complete",
        current: { id: target.id },
      });
      expect(preview.proposed).toMatchObject(
        kind === "group"
          ? { inbound_ids: [] }
          : {
              is_hidden: true,
              group_mode: "ALLOW_ONLY",
              group_ids: [catalog.groups[1].id],
              address: catalog.hosts[0].address,
            }
      );
      const revalidation = unwrap(
        await client.api("/admin/console/resources/revalidate", {
          method: "POST",
          body: JSON.stringify({ change: draft, expected_fingerprint: preview.fingerprint }),
        })
      );
      expect(revalidation).toMatchObject({ valid: true, reason: "unchanged" });
      expect(consoleResourceCatalogFixture()).toEqual(catalog);
      expect(
        consoleResourceDraftPreviewFixture(initialDraft(catalog, target)!).fingerprint
      ).not.toBe(preview.fingerprint);
    }
  );

  it("rejects null, missing pairs, duplicate identifiers and endpoint fields in the safe Host mock", () => {
    const catalog = consoleResourceCatalogFixture();
    const draft = initialDraft(catalog, { kind: "host", id: catalog.hosts[0].id })!;
    if (draft.operation !== "host_update") throw new Error("wrong fixture");
    for (const patch of [
      { ...draft.patch, inbound_id: null },
      { ...draft.patch, group_mode: undefined },
      { ...draft.patch, node_ids: [catalog.nodes[0].id, catalog.nodes[0].id] },
      { ...draft.patch, address: "changed.test" },
    ])
      expect(
        consoleResourcePreviewDemoResponse("/admin/console/resources/preview", {
          method: "POST",
          body: JSON.stringify({ change: { ...draft, patch } }),
        })
      ).toEqual({ ok: false, error: "invalid_request" });
    expect(
      consoleResourceDraftPreviewFixture({
        ...draft,
        patch: { ...draft.patch, inbound_id: catalog.profiles[1].inbounds[0].id },
      })
    ).toMatchObject({ coverage: "partial", fingerprint: null });
  });
  it.each(["node_enable", "node_disable", "node_restart"] as const)(
    "previews %s without mutating inventory",
    async (operation) => {
      const before = JSON.stringify(consoleNodeFixture);
      const body: components["schemas"]["ConsoleResourcePreviewBody"] = {
        change: { ...change, operation },
      };
      const result = unwrap(
        await client.api("/admin/console/resources/preview", {
          method: "POST",
          body: JSON.stringify(body),
        })
      );
      expect(result).toMatchObject({
        change: body.change,
        execution_available: false,
        coverage: "complete",
        current: { is_disabled: false },
        proposed: { is_disabled: operation === "node_disable" },
      });
      expect(result.affected_service_ids).toEqual(
        result.direct.services.map((service) => service.service_id)
      );
      expect(result.affected_customer_ids).toEqual([
        ...new Set(result.direct.services.map((service) => service.customer_id)),
      ]);
      expect(JSON.stringify(consoleNodeFixture)).toBe(before);
    }
  );

  it.each(["unchanged", "changed", "incomplete"] as const)(
    "returns %s revalidation using generated response types",
    async (reason) => {
      const body: components["schemas"]["ConsoleResourceRevalidateBody"] = {
        change:
          reason === "incomplete"
            ? { ...change, target_id: "10000000-0000-0000-0000-000000000002" }
            : change,
        expected_fingerprint:
          reason === "changed"
            ? "a".repeat(64)
            : consoleResourcePreviewFixture(change).fingerprint!,
      };
      const result = unwrap(
        await client.api("/admin/console/resources/revalidate", {
          method: "POST",
          body: JSON.stringify(body),
        })
      );
      expect(result).toMatchObject({
        valid: reason === "unchanged",
        reason,
        preview: { execution_available: false },
      });
      if (reason === "incomplete")
        expect(result.preview).toMatchObject({
          coverage: "partial",
          current: null,
          proposed: null,
          blockers: ["target_not_found"],
        });
    }
  );

  it.each([
    { change: { ...change, force_restart: true } },
    { change: { ...change, force_restart: null } },
    { change: { ...change, target_id: "not-a-uuid" } },
    { change: { ...change, operation: "execute" } },
    { change: { ...change, credentials: "not_allowed" } },
    { change, execute: true },
  ])("rejects invalid bodies rather than accepting a wider protocol: %j", (body) => {
    expect(
      consoleResourcePreviewDemoResponse("/admin/console/resources/preview", {
        method: "POST",
        body: JSON.stringify(body),
      })
    ).toEqual({ ok: false, error: "invalid_request" });
  });

  it("keeps execution and unrelated routes outside this read-only handler", () => {
    expect(
      consoleResourcePreviewDemoResponse("/admin/console/resources/execute", { method: "POST" })
    ).toBeUndefined();
    expect(
      consoleResourcePreviewDemoResponse("/admin/console/resources/preview", {})
    ).toMatchObject({ ok: false });
    expect(
      consoleResourcePreviewDemoResponse("/admin/console/resources/preview", {
        method: "POST",
        body: "{",
      })
    ).toMatchObject({ ok: false });
    expect(
      consoleResourcePreviewDemoResponse("/admin/console/resources/revalidate", {
        method: "POST",
        body: JSON.stringify({ change, expected_fingerprint: "bad" }),
      })
    ).toMatchObject({ ok: false });
  });
});
