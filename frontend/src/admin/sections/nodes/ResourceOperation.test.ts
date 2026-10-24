import { readFileSync } from "node:fs";
import { render } from "svelte/server";
import { describe, expect, it } from "vitest";
import { resolveLocaleKey } from "$lib/webapp/constants";
import { resourceActions } from "$lib/admin/resourceOperations";
import {
  resourceOperationFixture,
  resourceOperationPreviewFixture,
} from "$lib/webapp/mockApi/consoleResourceOperations";
import ResourceOperationStatus from "./ResourceOperationStatus.svelte";
import ResourceOperationEvidence from "./ResourceOperationEvidence.svelte";
import ResourceCreateForm from "./ResourceCreateForm.svelte";
import ResourceObservedValues from "./ResourceObservedValues.svelte";
import ConsoleResourcePreviewResult from "./ConsoleResourcePreviewResult.svelte";
import ConsoleResourceCatalogTable from "./ConsoleResourceCatalogTable.svelte";
import NodeDeployment from "./NodeDeployment.svelte";
import { consoleResourceCatalogFixture } from "$lib/webapp/mockApi/consoleResourcePreview";

const at = (key: string) => key;
describe("resource operation presentation", () => {
  it.each([
    ["en", "Resource name"],
    ["ru", "Название ресурса"],
    ["zh-hans", "资源名称"],
  ])(
    "uses the resource name label across create, preview, readback and catalog in %s",
    (language, name) => {
      const locale: Record<string, string> = JSON.parse(
        readFileSync(new URL(`../../../../../locales/${language}.json`, import.meta.url), "utf8")
      );
      const at = (key: string) => locale[resolveLocaleKey(`admin_${key}`)] ?? key;
      expect(at("console_resource_name")).toBe(name);
      const catalog = consoleResourceCatalogFixture();
      const preview = resourceOperationPreviewFixture({
        operation: "group_create",
        name: "QA-group",
        inbound_ids: [],
      });
      const form = render(ResourceCreateForm, {
        props: { kind: "group", at, catalog, onReview: () => {} },
      }).body;
      expect(form).toContain(`aria-label="${name}"`);
      expect(form).not.toContain(at("services_name"));
      const review = render(ConsoleResourcePreviewResult, {
        props: {
          preview,
          at,
          currentUrl: "https://console.test/admin/node-resources",
          serviceHref: () => "#",
          onOpenService: () => {},
          onOpenUserCard: () => {},
        },
      }).body;
      const observed = render(ResourceObservedValues, {
        props: { at, values: preview.proposed! },
      }).body;
      for (const result of [review, observed])
        expect(result).toMatch(
          new RegExp(`data-label="${at("console_resource_field")}"[^>]*>${name}</td>`)
        );
      const table = render(ConsoleResourceCatalogTable, {
        props: { at, rows: catalog.groups, kind: "group", onOpen: () => {} },
      }).body;
      expect(table).toContain(`data-label="${name}"`);
      expect(table).not.toContain(at("services_name"));
    }
  );

  it("keeps queued, upstream receipt, configuration and runtime results distinct", () => {
    const operation = resourceOperationFixture();
    const pending = render(ResourceOperationStatus, { props: { operation, at } }).body;
    expect(pending).toContain("resource_ops_status_pending");
    expect(pending).toContain("resource_ops_not_sent");
    expect(pending).not.toContain("resource_ops_status_succeeded");
    operation.status = "succeeded";
    operation.gate_active = false;
    operation.completed_at = new Date().toISOString();
    operation.attempts = [{ number: 1, started_at: operation.created_at, receipt: "accepted" }];
    operation.observation = {
      observed_at: operation.created_at,
      configuration: "matched",
      values: {
        ...operation.preview.proposed!,
        name: "Real readback name",
        address: "readback.example",
        port: 8443,
      },
      correlation: "known_uuid",
      restart: "accepted_unverified",
      runtime: "unverified",
    };
    const html = render(ResourceOperationStatus, { props: { operation, at } }).body;
    for (const text of [
      "resource_ops_status_succeeded",
      "resource_ops_gate_released",
      "resource_ops_configuration_matched",
      "resource_ops_restart_accepted_unverified",
      "resource_ops_runtime_unverified",
      "Real readback name",
      "readback.example",
      "8443",
    ])
      expect(html).toContain(text);
    expect(html).not.toContain("resource_ops_status_pending");
  });

  it("never prints raw unknown errors, enums, evidence digests or added private fields", () => {
    const operation = resourceOperationFixture();
    operation.error_code = "private_error_credential";
    Object.assign(operation, { status: "private_status", raw_config: "raw_private_config" });
    operation.evidence = [
      {
        actor_id: 42,
        attempt: 1,
        result: "applied",
        target_id: null,
        evidence_digest: "f".repeat(64),
        observed_at: operation.created_at,
        recorded_at: operation.created_at,
        provenance: "administrator_attestation",
        original_request_terminated: null,
      },
    ];
    const html = render(ResourceOperationStatus, { props: { operation, at } }).body;
    expect(html).toContain("resource_ops_attestation");
    expect(html).toContain("console_unknown");
    expect(html).toContain("resource_ops_error_unknown");
    for (const secret of [
      "private_error_credential",
      "private_status",
      "raw_private_config",
      "f".repeat(64),
    ])
      expect(html).not.toContain(secret);
  });

  it.each(["en", "ru", "zh-hans"])(
    "keeps a removed target, released protection and unverified service state distinct in %s",
    (language) => {
      const locale: Record<string, string> = JSON.parse(
        readFileSync(new URL(`../../../../../locales/${language}.json`, import.meta.url), "utf8")
      );
      const at = (key: string) => locale[resolveLocaleKey(`admin_${key}`)] ?? key;
      const operation = resourceOperationFixture();
      operation.status = "unknown";
      operation.attempts = [{ number: 1, started_at: operation.created_at, receipt: "unknown" }];
      operation.observation = {
        observed_at: operation.created_at,
        configuration: "missing",
        values: null,
        runtime: "unverified",
        restart: "not_requested",
        correlation: "known_uuid",
      };
      const unresolved = render(ResourceOperationStatus, { props: { operation, at } }).body;
      expect(unresolved).toContain(at("resource_ops_status_unknown"));
      expect(unresolved).toContain(at("resource_ops_gate_held"));
      expect(unresolved).toContain(at("resource_ops_configuration_missing"));
      expect(unresolved).not.toContain(at("resource_ops_status_succeeded"));
      expect(unresolved).not.toContain(at("resource_ops_gate_released"));

      operation.status = "failed";
      operation.error_code = "resource_target_removed";
      operation.gate_active = false;
      operation.completed_at = operation.created_at;
      operation.evidence = [
        {
          actor_id: 42,
          attempt: 1,
          result: "externally_removed",
          target_id: operation.target_id,
          evidence_digest: "b".repeat(64),
          observed_at: operation.created_at,
          recorded_at: operation.created_at,
          provenance: "administrator_attestation",
          original_request_terminated: true,
        },
      ];
      const html = render(ResourceOperationStatus, { props: { operation, at } }).body;
      for (const key of [
        "resource_ops_status_failed",
        "resource_ops_error_removed",
        "resource_ops_removed_warning",
        "resource_ops_configuration_missing",
        "resource_ops_gate_released",
        "resource_ops_runtime_unverified",
        "resource_ops_attestation_title",
        "resource_ops_evidence_externally_removed",
      ])
        expect(html).toContain(at(key));
      expect(html).toContain(`${at("resource_ops_actor")}: 42`);
      expect(html).not.toContain("b".repeat(64));
      expect(html).not.toContain("externally_removed");
      expect(html).not.toContain(at("resource_ops_status_succeeded"));
      expect(html).not.toContain(at("resource_ops_gate_held"));
    }
  );

  it("starts manual evidence with empty actual-record fields and no enabled write", () => {
    const operation = resourceOperationFixture();
    operation.status = "unknown";
    operation.attempts = [{ number: 1, started_at: operation.created_at, receipt: "unknown" }];
    const html = render(ResourceOperationEvidence, {
      props: {
        operation,
        at,
        busy: false,
        onsubmit: () => {
          throw new Error("SSR cannot submit");
        },
      },
    }).body;
    expect(html).toContain('pattern="[a-f0-9]{64}"');
    expect(html).toMatch(/type="submit"[^>]*disabled/);
    expect(html).toContain("resource_ops_attestation");
    expect(html).not.toContain(operation.created_at);
  });

  it("renders onboarding/create controls without API calls or generated credentials", () => {
    const api = async () => {
      throw new Error("SSR cannot request credentials");
    };
    const deployment = render(NodeDeployment, { props: { api, at, available: false } }).body;
    expect(deployment).toContain("resource_ops_deployment_scope");
    expect(deployment).toMatch(/type="submit"[^>]*disabled/);
    expect(deployment).not.toContain("SECRET_KEY");
    for (const kind of ["node", "group", "host"] as const) {
      const html = render(ResourceCreateForm, {
        props: { kind, at, catalog: consoleResourceCatalogFixture(), onReview: () => {} },
      }).body;
      expect(html).toContain("resource_ops_complete_fields");
      expect(html).toMatch(/type="submit"[^>]*disabled/);
      if (kind === "group") expect(html).toContain('pattern="[A-Za-z0-9_\\s-]+"');
    }
    const source = readFileSync(new URL("NodeDeployment.svelte", import.meta.url), "utf8");
    expect(source).toContain("<Textarea");
    expect(source).not.toContain("<textarea");
    expect(source).not.toMatch(/localStorage|sessionStorage|console\./);
  });

  it.each(["en", "ru", "zh-hans"])(
    "has actual %s translations for controls and safe dynamic states",
    (language) => {
      const locale: Record<string, string> = JSON.parse(
        readFileSync(new URL(`../../../../../locales/${language}.json`, import.meta.url), "utf8")
      );
      const keys = new Set<string>(
        resourceActions.map((action) => `resource_ops_action_${action}`)
      );
      const enums = {
        status: ["pending", "unknown", "failed", "succeeded", "superseded"],
        configuration: ["matched", "different", "missing", "unavailable"],
        restart: ["not_requested", "accepted_unverified", "may_be_noop", "unknown"],
        correlation: [
          "response_uuid",
          "creation_marker",
          "administrator_attestation",
          "known_uuid",
          "unresolved",
        ],
        receipt: ["unknown", "accepted", "rejected"],
        evidence: ["applied", "not_applied", "partial", "externally_removed"],
      };
      for (const [group, values] of Object.entries(enums))
        for (const value of values) keys.add(`resource_ops_${group}_${value}`);
      for (const file of [
        "ResourceOperationDetail.svelte",
        "ResourceOperationEvidence.svelte",
        "ResourceOperationList.svelte",
        "ResourceOperationReview.svelte",
        "ResourceOperationStatus.svelte",
        "ResourceOperationSubmit.svelte",
        "ResourceObservedValues.svelte",
        "ResourceCreateDialog.svelte",
        "ResourceCreateForm.svelte",
        "NodeDeployment.svelte",
        "NodeOnboardingProgress.svelte",
        "../../../lib/admin/resourceOperations.ts",
        "../../../lib/admin/resourceIntent.ts",
      ])
        for (const match of readFileSync(new URL(file, import.meta.url), "utf8").matchAll(
          /"((?:resource_ops|console|services)_[a-z_]+)"/g
        ))
          keys.add(match[1]);
      for (const key of keys)
        expect(locale[resolveLocaleKey(`admin_${key}`)], `${language}: ${key}`).toBeTruthy();
      expect(locale.admin_resource_ops_deployment_scope).toContain("3.4.2");
      expect(locale.admin_resource_ops_deployment_scope).toContain("r3");
    }
  );
});
