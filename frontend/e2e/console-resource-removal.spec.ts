import { expect, test, type Locator, type Page } from "@playwright/test";
import { resourceOperationFixture } from "../src/lib/webapp/mockApi/consoleResourceOperations";
import {
  capture,
  choose,
  installResources,
  labels,
  observed,
  query,
  type ResourceHarness,
} from "./fixtures/resource-operations";

// F07 / UC-08 / UA-14: browser consumers of simulated readback, not backend execution evidence.
for (const language of ["en", "ru", "zh-hans"] as const)
  for (const width of [1440, 390]) {
    const label = labels(language);
    test.describe(`${language} external resource removal at ${width}`, () => {
      test.use({ viewport: { width, height: 960 }, timezoneId: "UTC" });
      const button = (host: Locator, key: string) =>
        host.getByRole("button", { name: label(key), exact: true });
      const field = (host: Locator, key: string) => host.getByLabel(label(key), { exact: true });
      const checkbox = (host: Locator, key: string) =>
        host.getByRole("checkbox", { name: label(key), exact: true });
      const digest = "b".repeat(64);
      const evidenceWrites = (fixture: ResourceHarness) =>
        fixture.writes().filter((call) => call.path.endsWith("/evidence"));

      async function openUnknown(
        page: Page,
        fixture: ResourceHarness,
        configuration: "missing" | "unavailable" = "missing"
      ) {
        const targetId = fixture.catalog.hosts[0].id;
        if (!targetId) throw new Error("The removal fixture needs the original Host UUID");
        const operation = observed(
          resourceOperationFixture({
            operation: "host_update",
            target_id: targetId,
            patch: { address: "replacement-route.example.test" },
          }),
          "unknown"
        );
        const currentMinute = Math.floor(Date.now() / 60_000) * 60_000;
        operation.created_at = new Date(currentMinute - 10 * 60_000).toISOString();
        operation.attempts = [
          {
            number: 1,
            started_at: new Date(currentMinute - 9 * 60_000).toISOString(),
            receipt: "unknown",
          },
        ];
        operation.observation = {
          observed_at: new Date(currentMinute - 60_000).toISOString(),
          configuration,
          values: null,
          runtime: "unverified",
          restart: "not_requested",
          correlation: "known_uuid",
        };
        expect(operation.preview.coverage).toBe("complete");
        fixture.seed(operation);
        await page.goto(
          `/demo/runtime/admin/console-operations${query}&operations_view=resources&resource_operation_id=${operation.id}`
        );
        const record = page.getByRole("dialog", {
          name: label("resource_ops_detail"),
          exact: true,
        });
        await expect(record.locator(".resource-operation-detail")).toHaveAttribute(
          "aria-busy",
          "false"
        );
        await expect(record).toContainText(operation.id);
        await expect(record).toContainText(label("resource_ops_status_unknown"));
        await expect(record).toContainText(label(`resource_ops_configuration_${configuration}`));
        await expect(record).toContainText(label("resource_ops_gate_held"));
        return { record, operation, targetId };
      }

      async function fillEvidenceTime(record: Locator, timestamp = Date.now()) {
        const date = new Date(Math.floor(timestamp / 60_000) * 60_000);
        const form = record.locator(".resource-evidence");
        const clear = form.getByRole("button", {
          name: `${label("clear")}: ${label("services_exit_checked_at")}`,
          exact: true,
        });
        if (await clear.count()) await clear.click();
        for (const [part, value] of [
          ["year", String(date.getUTCFullYear())],
          ["month", String(date.getUTCMonth() + 1).padStart(2, "0")],
          ["day", String(date.getUTCDate()).padStart(2, "0")],
          ["hour", String(date.getUTCHours()).padStart(2, "0")],
          ["minute", String(date.getUTCMinutes()).padStart(2, "0")],
        ]) {
          const segment = form.locator(`[data-segment="${part}"]`);
          await segment.focus();
          await segment.pressSequentially(value);
          await expect.poll(async () => Number(await segment.textContent())).toBe(Number(value));
        }
        return date.toISOString();
      }

      async function fillEvidence(record: Locator, targetId: string) {
        const checkedAt = await fillEvidenceTime(record);
        await field(record, "replacement_digest").fill(digest);
        await field(record, "resource_ops_target_id").fill(targetId);
        await checkbox(record, "resource_ops_request_terminated").check();
        await checkbox(record, "resource_ops_attest_confirm").check();
        return checkedAt;
      }

      async function expectClosed(record: Locator, targetId: string) {
        const status = record.locator(".resource-operation-status");
        for (const key of [
          "resource_ops_status_failed",
          "resource_ops_error_removed",
          "resource_ops_configuration_missing",
          "resource_ops_gate_released",
          "resource_ops_runtime_unverified",
          "resource_ops_attestation_title",
          "resource_ops_attestation",
        ])
          await expect(status).toContainText(label(key));
        await expect(status.getByRole("note")).toHaveText(label("resource_ops_removed_warning"));
        await expect(status).toContainText(targetId);
        const evidence = status.getByRole("listitem");
        await expect(evidence).toHaveCount(1);
        await expect(evidence).toContainText(label("resource_ops_evidence_externally_removed"));
        await expect(evidence).toContainText("#1");
        await expect(evidence).toContainText(`${label("resource_ops_actor")}: 910001`);
        await expect(status).not.toContainText(digest);
        await expect(status).not.toContainText(label("resource_ops_status_succeeded"));
        await expect(status).not.toContainText(label("resource_ops_gate_held"));
        for (const key of [
          "resource_ops_retry_preview",
          "resource_ops_retry",
          "resource_ops_recovery_preview",
          "resource_ops_reconcile",
          "resource_ops_submit",
        ])
          await expect(button(record, key)).toHaveCount(0);
        await expect(record.locator(".resource-evidence")).toHaveCount(0);
      }

      test("requires every original-target attestation and retains closure without claiming recovery", async ({
        page,
      }, info) => {
        const fixture = await installResources(page, language);
        const { record, operation, targetId } = await openUnknown(page, fixture);
        await expect(record).not.toContainText(label("resource_ops_status_succeeded"));
        await button(record, "resource_ops_reconcile").click();
        await expect(record.locator(".resource-operation-detail")).toHaveAttribute(
          "aria-busy",
          "false"
        );
        await expect(record).toContainText(label("resource_ops_error_manual"));
        await expect(record).toContainText(label("resource_ops_gate_held"));
        const unresolved = await fixture.read(operation.id);
        expect(unresolved).toMatchObject({
          status: "unknown",
          can_retry: false,
          gate_active: true,
          observation: { configuration: "missing", values: null },
          evidence: [],
        });
        const form = record.locator(".resource-evidence");
        const save = button(form, "save");
        await expect(save).toBeDisabled();
        await choose(
          page,
          record,
          label("resource_ops_evidence_result"),
          label("resource_ops_evidence_externally_removed"),
          info,
          true
        );
        await expect(form.getByRole("note")).toHaveText(label("resource_ops_removed_warning"));
        await expect(field(form, "resource_ops_target_id")).toHaveValue("");
        await expect(form.getByRole("checkbox")).toHaveCount(2);
        await fillEvidence(record, targetId);
        await expect(save).toBeEnabled();

        for (const value of ["", "70000000-0000-0000-0000-000000000099", "not-a-uuid"]) {
          await field(form, "resource_ops_target_id").fill(value);
          await expect(save).toBeDisabled();
          await field(form, "replacement_digest").press("Enter");
          expect(evidenceWrites(fixture)).toHaveLength(0);
        }
        await field(form, "resource_ops_target_id").fill(targetId);
        await expect(save).toBeEnabled();
        for (const value of ["", "b".repeat(63), "g".repeat(64)]) {
          await field(form, "replacement_digest").fill(value);
          await expect(save).toBeDisabled();
          await field(form, "resource_ops_target_id").press("Enter");
          expect(evidenceWrites(fixture)).toHaveLength(0);
        }
        await field(form, "replacement_digest").fill(digest);
        await expect(save).toBeEnabled();
        await form
          .getByRole("button", {
            name: `${label("clear")}: ${label("services_exit_checked_at")}`,
            exact: true,
          })
          .click();
        await expect(save).toBeDisabled();
        await field(form, "replacement_digest").press("Enter");
        expect(evidenceWrites(fixture)).toHaveLength(0);
        await fillEvidenceTime(record);
        await expect(save).toBeEnabled();
        for (const key of ["resource_ops_request_terminated", "resource_ops_attest_confirm"]) {
          await checkbox(form, key).uncheck();
          await expect(save).toBeDisabled();
          await field(form, "replacement_digest").press("Enter");
          expect(evidenceWrites(fixture)).toHaveLength(0);
          await checkbox(form, key).check();
          await expect(save).toBeEnabled();
        }
        // Keep stale evidence after the attempt so only the five-minute age guard rejects it.
        const expiredAt = await fillEvidenceTime(record, Date.now() - 6 * 60_000);
        expect(Date.parse(expiredAt)).toBeGreaterThan(Date.parse(operation.attempts[0].started_at));
        expect(Date.now() - Date.parse(expiredAt)).toBeGreaterThan(5 * 60_000);
        await expect(save).toBeDisabled();
        await field(form, "replacement_digest").press("Enter");
        expect(evidenceWrites(fixture)).toHaveLength(0);
        const checkedAt = await fillEvidenceTime(record);
        expect(Date.parse(checkedAt)).toBeGreaterThan(Date.parse(operation.attempts[0].started_at));
        expect(Date.parse(checkedAt)).toBeLessThanOrEqual(Date.now());
        expect(Date.now() - Date.parse(checkedAt)).toBeLessThan(5 * 60_000);
        await expect(save).toBeEnabled();
        await capture(page, record, info, "removal-evidence-complete");
        await save.click();
        await expectClosed(record, targetId);
        expect(evidenceWrites(fixture)).toHaveLength(1);
        expect(evidenceWrites(fixture)[0]).toEqual({
          path: `/admin/console/resources/operations/${operation.id}/evidence`,
          method: "POST",
          body: {
            expected_version: unresolved.version,
            attempt: 1,
            result: "externally_removed",
            target_id: targetId,
            evidence_digest: digest,
            checked_at: checkedAt,
            original_request_terminated: true,
          },
        });
        const closed = await fixture.read(operation.id);
        expect(closed).toMatchObject({
          status: "failed",
          error_code: "resource_target_removed",
          gate_active: false,
          can_retry: false,
          requires_manual_reconciliation: false,
          target_id: targetId,
          observation: { configuration: "missing", values: null },
          evidence: [
            {
              actor_id: 910001,
              attempt: 1,
              result: "externally_removed",
              target_id: targetId,
              evidence_digest: digest,
              original_request_terminated: true,
              observed_at: checkedAt,
              provenance: "administrator_attestation",
            },
          ],
        });
        const evidenceText = await record.locator(".resource-operation-status li").innerText();
        await button(record, "refresh").click();
        await expect(record.locator(".resource-operation-detail")).toHaveAttribute(
          "aria-busy",
          "false"
        );
        await expectClosed(record, targetId);
        await page.reload();
        await expect(record.locator(".resource-operation-detail")).toHaveAttribute(
          "aria-busy",
          "false"
        );
        await expectClosed(record, targetId);
        await expect(record.locator(".resource-operation-status li")).toHaveText(evidenceText);
        await capture(page, record, info, "removed-record-after-reload");
        await record.locator(".dialog-close-button").click();
        const row = page.locator(`[data-resource-operation-id="${operation.id}"] button`);
        await expect(row).toBeFocused();
        await row.press("Enter");
        await expectClosed(record, targetId);
        expect(await fixture.read(operation.id)).toEqual(closed);
        expect(fixture.writes().map((call) => call.path)).toEqual([
          `/admin/console/resources/operations/${operation.id}/reconcile`,
          `/admin/console/resources/operations/${operation.id}/evidence`,
        ]);
        fixture.finish();
      });

      test("unavailable observation keeps protection and the entered evidence after rejection", async ({
        page,
      }, info) => {
        const fixture = await installResources(page, language);
        const { record, operation, targetId } = await openUnknown(page, fixture, "unavailable");
        await choose(
          page,
          record,
          label("resource_ops_evidence_result"),
          label("resource_ops_evidence_externally_removed")
        );
        const checkedAt = await fillEvidence(record, targetId);
        expect(Date.parse(checkedAt)).toBeGreaterThan(Date.parse(operation.attempts[0].started_at));
        expect(Date.parse(checkedAt)).toBeLessThanOrEqual(Date.now());
        expect(Date.now() - Date.parse(checkedAt)).toBeLessThan(5 * 60_000);
        await button(record.locator(".resource-evidence"), "save").click();
        await expect(record).toContainText(label("resource_ops_error_incomplete"));
        await expect(record).toContainText(label("resource_ops_gate_held"));
        await expect(record).toContainText(label("resource_ops_status_unknown"));
        await expect(record).not.toContainText(label("resource_ops_error_removed"));
        await expect(field(record, "resource_ops_target_id")).toHaveValue(targetId);
        await expect(field(record, "replacement_digest")).toHaveValue(digest);
        await expect(checkbox(record, "resource_ops_request_terminated")).toBeChecked();
        await expect(checkbox(record, "resource_ops_attest_confirm")).toBeChecked();
        expect(await fixture.read(operation.id)).toEqual({ ...operation, ok: true });
        expect(evidenceWrites(fixture)).toHaveLength(1);
        expect(evidenceWrites(fixture)[0].body).toEqual({
          expected_version: operation.version,
          attempt: 1,
          result: "externally_removed",
          target_id: targetId,
          evidence_digest: digest,
          checked_at: checkedAt,
          original_request_terminated: true,
        });
        await capture(page, record, info, "removal-insufficient-observation");
        fixture.finish();
      });
    });
  }
