import { expect, test, type Locator, type Page } from "@playwright/test";
import { resourceOperationFixture } from "../src/lib/webapp/mockApi/consoleResourceOperations";
import { consoleNodeFixture } from "../src/lib/admin/consoleNodesFixtures";
import {
  capture,
  choose,
  evidenceTime,
  installResources,
  labels,
  observed,
  query,
  type ResourceHarness,
} from "./fixtures/resource-operations";

for (const language of ["en", "ru", "zh-hans"] as const)
  for (const width of [1440, 390]) {
    const label = labels(language);
    test.describe(`${language} resources at ${width}`, () => {
      test.use({ viewport: { width, height: 960 }, timezoneId: "UTC" });
      const button = (host: Locator, key: string) =>
        key === "close"
          ? host.locator(".dialog-close-button")
          : host.getByRole("button", { name: label(key), exact: true });
      const field = (host: Locator, key: string) => host.getByLabel(label(key), { exact: true });
      const dialog = (page: Page, key: string) =>
        page.getByRole("dialog", { name: label(key), exact: true });
      async function startCreate(page: Page, kind: "node" | "group" | "host") {
        await page.goto(
          `/demo/runtime/admin/${kind === "node" ? "nodes" : "node-resources"}${query}${kind === "node" ? "" : `&resources_kind=${kind}`}`
        );
        const root = page.locator(kind === "node" ? ".console-nodes" : ".console-resources");
        const trigger = button(root, `resource_ops_action_${kind}_create`);
        await trigger.focus();
        await trigger.press("Enter");
        const target = dialog(page, `resource_ops_action_${kind}_create`);
        await expect(target.locator(".resource-create-form")).toBeVisible();
        return { target, trigger };
      }
      async function groupReview(page: Page) {
        const { target, trigger } = await startCreate(page, "group");
        await field(target, "console_resource_name").fill("QA-group");
        await target.locator(".resource-create-form").getByRole("checkbox").first().check();
        await button(target.locator(".resource-create-form"), "console_resource_preview").click();
        await expect(target.locator(".resource-preview-result")).toBeVisible();
        return { target, trigger };
      }
      async function confirm(target: Locator) {
        await target
          .getByRole("checkbox", { name: label("console_resource_confirm"), exact: true })
          .check();
        await expect(button(target, "resource_ops_submit")).toBeEnabled();
        await button(target, "resource_ops_submit").click();
      }
      async function openRecord(page: Page, id: string) {
        await page.goto(
          `/demo/runtime/admin/console-operations${query}&operations_view=resources&resource_operation_id=${id}&user_id=910002&phase=delivery`
        );
        const target = dialog(page, "resource_ops_detail");
        await expect(target.locator(".resource-operation-detail")).toHaveAttribute(
          "aria-busy",
          "false"
        );
        await expect(target).toContainText(id);
        return target;
      }
      const startWrites = (fixture: ResourceHarness) =>
        fixture.writes().filter((call) => call.path === "/admin/console/resources/operations");

      test("global directory keeps long identities, keyboard menus and service return context", async ({
        page,
      }, info) => {
        const fixture = await installResources(page, language);
        await page.goto(`/demo/runtime/admin/nodes${query}`);
        await expect(page.locator(".console-nodes")).toBeVisible();
        const toggle = page.locator(".admin-mobile-toggle");
        if ((await toggle.isVisible()) && (await toggle.getAttribute("aria-expanded")) !== "true")
          await toggle.click();
        await page.locator('.admin-sidebar [data-admin-section="node-resources"]').click();
        const root = page.locator(".console-resources");
        await expect(root).toHaveAttribute("aria-busy", "false");
        await expect(root.locator("[data-resource-id]")).toHaveCount(2);
        await expect(root).toContainText(fixture.longName);
        await expect(root.locator("[data-resource-card]")).toHaveCount(2);
        await expect(root.locator(".catalog-status details")).not.toHaveAttribute("open", "");
        await button(root, "console_nodes_view_table").click();
        await expect(root.locator("[data-resource-card]")).toHaveCount(0);
        await expect(root.locator("[data-resource-id]")).toHaveCount(2);
        await button(root, "console_catalog_view_cards").click();
        await capture(page, root, info, "relationship-cards");
        const trigger = root.locator(`[data-resource-id="${fixture.catalog.groups[0].id}"] button`);
        await trigger.focus();
        await trigger.press("Enter");
        let detail = dialog(page, "console_catalog_detail");
        await expect(detail).toContainText(fixture.catalog.groups[0].id);
        await expect(detail.locator("[data-resource-inbound]")).toHaveCount(1);
        await expect(
          detail.locator(`a[href*="node_id=${fixture.catalog.nodes[0].id}"]`)
        ).toBeVisible();
        const hostLink = detail.locator(`a[href*="resource_id=${fixture.catalog.hosts[0].id}"]`);
        await expect(hostLink).toBeVisible();
        await capture(page, detail, info, "group-detail");
        await hostLink.click();
        await expect(page).toHaveURL(/resources_kind=host/);
        await expect(
          detail.locator(`a[href*="resource_id=${fixture.catalog.groups[0].id}"]`)
        ).toBeVisible();
        await page.goBack();
        await page.reload();
        await expect(detail).toBeVisible();
        await button(detail, "close").click();
        await expect(trigger).toBeFocused();
        await choose(
          page,
          root,
          label("console_catalog_kind"),
          label("console_nodes_hosts"),
          info,
          true
        );
        await root.locator("[data-resource-id] button").click();
        detail = dialog(page, "console_catalog_detail");
        await expect(detail).toContainText("hk.example.test");
        await capture(page, detail, info, "host-detail");
        await button(detail, "close").click();
        await page.goto(
          `/demo/runtime/admin/console-operations${query}&user_id=910002&phase=delivery`
        );
        await expect(page.locator(".console-operations")).toHaveAttribute("aria-busy", "false");
        await choose(
          page,
          page.locator(".admin-content"),
          label("resource_ops_view"),
          label("resource_ops_title")
        );
        await expect(page.locator(".resource-operations-list")).toBeVisible();
        await choose(
          page,
          page.locator(".admin-content"),
          label("resource_ops_view"),
          label("resource_ops_service_view")
        );
        await expect(page).toHaveURL(/user_id=910002/);
        await expect(page).toHaveURL(/phase=delivery/);
        await expect(page.locator(".console-operations")).toBeVisible();
        expect(fixture.writes()).toHaveLength(0);
        fixture.finish();
      });

      test("partial relationship cards preserve unknowns and preview return focus", async ({
        page,
      }, info) => {
        const fixture = await installResources(page, language);
        fixture.catalog.coverage = "partial";
        fixture.catalog.nodes = [];
        fixture.catalog.hosts[0].is_disabled = null;
        fixture.catalog.hosts[0].is_hidden = true;
        await page.goto(`/demo/runtime/admin/node-resources${query}&resources_kind=host`);
        const root = page.locator(".console-resources");
        const card = root.locator("[data-resource-card]");
        await expect(card).toContainText(label("console_rel_unknown_nodes"));
        await expect(card).toContainText(label("console_rel_state_unknown"));
        await expect(card).toContainText(label("console_rel_hidden"));
        await capture(page, root, info, "partial-cards");
        await card.locator("[data-resource-id] button").click();
        const detail = dialog(page, "console_catalog_detail");
        await expect(detail.locator(".resource-relations")).toContainText(
          label("console_rel_partial")
        );
        await detail.locator(".resource-technical summary").click();
        await capture(page, detail, info, "partial-technical-details");
        await button(detail, "close").click();
        fixture.catalog.coverage = "complete";
        await page.reload();
        await root.locator("[data-resource-id] button").click();
        const previewTrigger = button(detail, "console_draft_host_open");
        await previewTrigger.click();
        const preview = page.getByRole("dialog").filter({ has: page.locator(".resource-draft") });
        await expect(preview).toBeVisible();
        await button(preview, "close").click();
        await expect(previewTrigger).toBeFocused();
        expect(fixture.writes()).toHaveLength(0);
        fixture.finish();
      });

      test("group creation permits correction after explicit rejection and records pending only", async ({
        page,
      }, info) => {
        const fixture = await installResources(page, language);
        const { target } = await groupReview(page);
        await expect(target).toContainText(label("console_resource_affected_services"));
        await expect(target).toContainText(label("console_resource_affected_customers"));
        await expect(button(target, "resource_ops_submit")).toBeDisabled();
        await capture(page, target, info, "group-confirmation");
        fixture.trace.fail = "reject";
        await confirm(target);
        await expect(target).toContainText(label("resource_ops_error_input"));
        expect(startWrites(fixture)).toHaveLength(1);
        await button(target, "resource_ops_edit_draft").click();
        await expect(field(target, "console_resource_name")).toHaveValue("QA-group");
        await field(target, "console_resource_name").fill("QA-corrected-group");
        await button(target.locator(".resource-create-form"), "console_resource_preview").click();
        await confirm(target);
        await expect(target).toContainText(label("resource_ops_status_pending"));
        await expect(target).toContainText(label("resource_ops_not_sent"));
        await expect(button(target, "resource_ops_submit")).toHaveCount(0);
        expect(startWrites(fixture)).toHaveLength(2);
        expect(startWrites(fixture)[1].body.change).toMatchObject({
          operation: "group_create",
          name: "QA-corrected-group",
          inbound_ids: [fixture.catalog.profiles[0].inbounds[0].id],
        });
        expect(startWrites(fixture)[1].body.idempotency_key).not.toBe(
          startWrites(fixture)[0].body.idempotency_key
        );
        await target
          .getByRole("link", { name: label("resource_ops_open_record"), exact: true })
          .click();
        const record = dialog(page, "resource_ops_detail");
        await expect(record).toContainText(label("resource_ops_status_pending"));
        await page.reload();
        await expect(record).toContainText(label("resource_ops_status_pending"));
        fixture.seed(observed(await fixture.row(), "succeeded"));
        await button(record, "refresh").first().click();
        await expect(record).toContainText(label("resource_ops_status_succeeded"));
        await expect(record).not.toContainText(label("resource_ops_status_pending"));
        await expect(record).toContainText(label("resource_ops_runtime_unverified"));
        await capture(page, record, info, "group-result");
        await button(record, "close").click();
        await expect(
          page.locator(`[data-resource-operation-id="${(await fixture.row()).id}"] button`)
        ).toBeFocused();
        fixture.finish();
      });

      test("Host creation exposes unknown readback and explicit administrator reconciliation", async ({
        page,
      }, info) => {
        const fixture = await installResources(page, language);
        const { target } = await startCreate(page, "host");
        await field(target, "console_resource_name").fill(
          language === "zh-hans"
            ? "长期独立客户端线路完整名称ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
            : "Client route ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        );
        await field(target, "console_nodes_address").fill("new-route.example.test");
        await field(target, "console_catalog_port").fill("8443");
        await choose(
          page,
          target,
          label("console_nodes_profile"),
          `${fixture.catalog.profiles[0].name} · ${fixture.catalog.profiles[0].id}`,
          info,
          true
        );
        await choose(
          page,
          target,
          label("console_nodes_inbounds"),
          `${fixture.catalog.profiles[0].inbounds[0].tag} · ${fixture.catalog.profiles[0].inbounds[0].id}`
        );
        await choose(
          page,
          target,
          label("console_draft_group_mode"),
          label("console_draft_allow_only"),
          undefined,
          true
        );
        await target
          .getByRole("checkbox", {
            name: `${fixture.catalog.groups[0].name} · ${fixture.catalog.groups[0].id}`,
            exact: true,
          })
          .check();
        await capture(page, target, info, "host-create");
        await button(target.locator(".resource-create-form"), "console_resource_preview").click();
        await confirm(target);
        await expect(target).toContainText(label("resource_ops_status_pending"));
        expect(startWrites(fixture)[0].body.change).toMatchObject({
          operation: "host_create",
          address: "new-route.example.test",
          port: 8443,
          group_mode: "ALLOW_ONLY",
          group_ids: [fixture.catalog.groups[0].id],
          is_disabled: true,
        });
        fixture.seed(observed(await fixture.row(), "unknown"));
        await target
          .getByRole("link", { name: label("resource_ops_open_record"), exact: true })
          .click();
        const record = dialog(page, "resource_ops_detail");
        await expect(record).toContainText(label("resource_ops_status_unknown"));
        await button(record, "resource_ops_reconcile").click();
        await expect(record).toContainText(label("resource_ops_error_manual"));
        await expect(record).toContainText(label("resource_ops_gate_held"));
        await choose(
          page,
          record,
          label("resource_ops_evidence_result"),
          label("resource_ops_evidence_applied"),
          info
        );
        await evidenceTime(record);
        await field(record, "replacement_digest").fill("a".repeat(64));
        await field(record, "resource_ops_target_id").fill("60000000-0000-0000-0000-000000000001");
        await record
          .getByRole("checkbox", { name: label("resource_ops_attest_confirm"), exact: true })
          .check();
        await capture(page, record, info, "unknown-evidence");
        fixture.trace.fail = "evidence";
        await button(record.locator(".resource-evidence"), "save").click();
        await expect(record).toContainText(label("resource_ops_error_evidence"));
        await expect(field(record, "replacement_digest")).toHaveValue("a".repeat(64));
        await field(record, "replacement_digest").fill("b".repeat(64));
        await button(record.locator(".resource-evidence"), "save").click();
        await expect(record).toContainText(label("resource_ops_status_succeeded"));
        await expect(record).toContainText(label("resource_ops_attestation_title"));
        await expect(record).toContainText(label("resource_ops_gate_released"));
        await expect(record).not.toContainText("b".repeat(64));
        const declarations = fixture.writes().filter((call) => call.path.endsWith("/evidence"));
        expect(declarations).toHaveLength(2);
        expect(declarations[1].body).toMatchObject({
          attempt: 1,
          result: "applied",
          target_id: "60000000-0000-0000-0000-000000000001",
          evidence_digest: "b".repeat(64),
          checked_at: "2026-10-23T01:00:00.000Z",
        });
        await capture(page, record, info, "reconciled-host");
        fixture.finish();
      });

      test("Node onboarding clears credentials on close and separates all verification stages", async ({
        page,
      }, info) => {
        const fixture = await installResources(page, language);
        let { target, trigger } = await startCreate(page, "node");
        const deployment = target.locator(".node-deployment");
        await field(deployment, "resource_ops_management_port").fill("2222");
        await button(deployment, "resource_ops_deployment_generate").click();
        await expect(field(deployment, "resource_ops_deployment_config")).toHaveValue(
          /remnawave\/node:3\.4\.2/
        );
        await expect(target).toContainText(label("resource_ops_deployment_scope"));
        const storage = await page.evaluate(() =>
          JSON.stringify({
            local: { ...localStorage },
            session: { ...sessionStorage },
            url: location.href,
          })
        );
        expect(storage).not.toContain("DEMO-NOT-A-REAL-NODE-CREDENTIAL");
        await capture(page, target, info, "deployment-guidance");
        await button(target, "close").click();
        await expect(trigger).toBeFocused();
        await trigger.click();
        target = dialog(page, "resource_ops_action_node_create");
        await expect(target.locator(".resource-create-form")).toBeVisible();
        await expect(field(target, "resource_ops_deployment_config")).toHaveCount(0);
        const form = target.locator(".resource-create-form");
        await field(form, "console_resource_name").fill("QA-registered-node");
        await field(form, "console_nodes_address").fill("node.example.test");
        await field(form, "resource_ops_management_port").fill("2222");
        await choose(
          page,
          form,
          label("console_nodes_profile"),
          `${fixture.catalog.profiles[0].name} · ${fixture.catalog.profiles[0].id}`,
          info
        );
        await form.getByRole("checkbox").first().check();
        await button(form, "console_resource_preview").click();
        await confirm(target);
        await expect(target).toContainText(label("resource_ops_status_pending"));
        expect(startWrites(fixture)[0].body.change).toMatchObject({
          operation: "node_create",
          name: "QA-registered-node",
          address: "node.example.test",
          port: 2222,
        });
        expect(JSON.stringify(startWrites(fixture)[0].body)).not.toContain("SECRET");
        fixture.seed(observed(await fixture.row(), "succeeded"));
        await target
          .getByRole("link", { name: label("resource_ops_open_record"), exact: true })
          .click();
        const record = dialog(page, "resource_ops_detail");
        await expect(record.locator(".onboarding-progress")).toContainText(
          label("resource_ops_onboarding_subscription")
        );
        await expect(record.locator(".onboarding-progress")).toContainText(
          label("console_nodes_status_online")
        );
        await capture(page, record, info, "node-onboarding-result");
        fixture.finish();
      });

      test("a lost start response survives refresh and resolves only the original idempotency key", async ({
        page,
      }, info) => {
        const fixture = await installResources(page, language);
        const { target } = await groupReview(page);
        fixture.trace.fail = "after";
        await confirm(target);
        await expect(target).toContainText(label("resource_ops_pending_intent"));
        await expect(target).not.toContainText("private_response_lost");
        const original = startWrites(fixture)[0].body;
        await page.goto(`/demo/runtime/admin/console-operations${query}&operations_view=resources`);
        const root = page.locator(".resource-operations-list");
        await expect(button(root, "resource_ops_resume_intent")).toBeEnabled();
        await page.reload();
        await expect(button(root, "resource_ops_resume_intent")).toBeEnabled();
        expect(startWrites(fixture)).toHaveLength(1);
        await capture(page, root, info, "unresolved-original-intent");
        await button(root, "resource_ops_resume_intent").click();
        const record = dialog(page, "resource_ops_detail");
        await expect(record).toContainText(label("resource_ops_status_pending"));
        expect(startWrites(fixture)).toHaveLength(2);
        expect(startWrites(fixture)[1].body).toEqual(original);
        expect((await fixture.row()).attempts).toEqual([]);
        expect(
          await page.evaluate(() => sessionStorage.getItem("my-vps-resource-intent:910001"))
        ).toBeNull();
        fixture.finish();
      });

      test("retry retains the same operation and restoration requires a new reviewed intention", async ({
        page,
      }, info) => {
        const fixture = await installResources(page, language);
        const failed = observed(resourceOperationFixture(), "failed", "before");
        fixture.seed(failed);
        let record = await openRecord(page, failed.id);
        await button(record, "resource_ops_retry_preview").click();
        await expect(record.locator(".resource-review .resource-preview-result")).toBeVisible();
        await record
          .getByRole("checkbox", { name: label("console_resource_confirm"), exact: true })
          .check();
        await button(record, "resource_ops_retry").click();
        await expect(record).toContainText(label("resource_ops_status_pending"));
        const retries = fixture.writes().filter((call) => call.path.endsWith("/retry"));
        expect(retries).toHaveLength(1);
        expect(retries[0].body).toEqual({
          expected_version: failed.version,
          expected_fingerprint: failed.preview.fingerprint,
        });
        fixture.seed(observed(await fixture.read(failed.id), "succeeded"));
        await button(record, "refresh").first().click();
        await button(record, "resource_ops_recovery_preview").click();
        await expect(record.locator(".resource-review .resource-preview-result")).toBeVisible();
        await expect(button(record, "resource_ops_submit")).toBeDisabled();
        await capture(page, record, info, "restoration-review");
        await confirm(record);
        await expect.poll(async () => (await fixture.row()).id).not.toBe(failed.id);
        record = dialog(page, "resource_ops_detail");
        await expect(record).toContainText(label("resource_ops_status_pending"));
        expect(startWrites(fixture)).toHaveLength(1);
        expect(startWrites(fixture)[0].body).toMatchObject({
          recovery_of: failed.id,
          change: {
            operation: "node_enable",
            target_id: consoleNodeFixture.id,
            force_restart: false,
          },
        });
        fixture.finish();
      });

      test("capability and changed fingerprints block writes; uncertain retry stays blocked", async ({
        page,
      }, info) => {
        const fixture = await installResources(page, language);
        fixture.trace.available = false;
        let { target } = await groupReview(page);
        await target
          .getByRole("checkbox", { name: label("console_resource_confirm"), exact: true })
          .check();
        await expect(button(target, "resource_ops_submit")).toBeDisabled();
        await expect(target).toContainText(label("resource_ops_error_disabled"));
        expect(startWrites(fixture)).toHaveLength(0);
        fixture.trace.available = true;
        await button(target, "close").click();
        ({ target } = await groupReview(page));
        fixture.trace.drift = true;
        await confirm(target);
        await expect(target).toContainText(label("resource_ops_error_changed"));
        expect(startWrites(fixture)).toHaveLength(0);
        fixture.trace.drift = false;
        const failed = observed(resourceOperationFixture(), "failed", "before");
        fixture.seed(failed);
        const record = await openRecord(page, failed.id);
        await button(record, "resource_ops_retry_preview").click();
        await expect(record.locator(".resource-review .resource-preview-result")).toBeVisible();
        await record
          .getByRole("checkbox", { name: label("console_resource_confirm"), exact: true })
          .check();
        fixture.trace.fail = "retry";
        await button(record, "resource_ops_retry").click();
        await expect(record).toContainText(label("resource_ops_command_unknown"));
        await expect(button(record, "resource_ops_retry_preview")).toBeDisabled();
        await button(record, "refresh").first().click();
        await expect(button(record, "resource_ops_retry_preview")).toBeDisabled();
        await expect(record).not.toContainText("private_upstream_credential");
        expect(fixture.writes().filter((call) => call.path.endsWith("/retry"))).toHaveLength(1);
        await capture(page, record, info, "uncertain-retry");
        fixture.finish();
      });
    });
  }
