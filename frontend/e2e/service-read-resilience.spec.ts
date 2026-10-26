import { expect, test } from "@playwright/test";
import {
  installServiceReads,
  nextTime,
  service,
  time,
  type Surface,
  serviceReadEvidence,
} from "./fixtures/service-reads";

test.afterEach(async ({ page }, info) => {
  const evidence = serviceReadEvidence.get(page);
  if (!evidence) return;
  await info.attach("service-http-evidence", {
    body: JSON.stringify(evidence, null, 2),
    contentType: "application/json",
  });
  expect(evidence.pageErrors).toEqual([]);
});

const surfaces: Surface[] = ["user", "customer", "global", "detail"];
const displayTime = (value: string) =>
  new Intl.DateTimeFormat("sv-SE", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
    timeZone: "Asia/Shanghai",
  }).format(new Date(value));

for (const surface of surfaces) {
  test(`H01 H11 ${surface}: same-query HTTP503 preserves the original snapshot and retry replaces it`, async ({
    page,
  }) => {
    const fixture = await installServiceReads(page, surface);
    fixture.state.total = 41;
    await fixture.goto();
    const root = fixture.root();
    if (surface === "customer") await root.locator(":scope > details > summary").click();
    await expect(root).toContainText(service.name);
    await expect(root).toContainText("23 GiB");
    await page.clock.setFixedTime(new Date("2026-10-25T03:00:00Z"));
    fixture.state.failure = fixture.state.detailFailure = 503;
    await fixture.refresh();
    const alert = root.getByRole("alert").first();
    await expect(alert).toContainText(
      fixture.label(
        surface === "user"
          ? "load_failed"
          : surface === "detail"
            ? "console_detail_failed"
            : "services_load_failed"
      )
    );
    await expect(alert).toContainText(
      displayTime(surface === "global" ? time : "2026-10-25T02:00:00Z")
    );
    await expect(alert).not.toContainText(displayTime("2026-10-25T03:00:00Z"));
    await expect(alert).toContainText(
      (surface === "global"
        ? fixture.copy.admin_services_snapshot_observed_stale
        : surface === "user"
          ? fixture.copy.wa_services_snapshot_stale
          : fixture.copy.admin_services_snapshot_stale
      ).replace("{time}", displayTime(surface === "global" ? time : "2026-10-25T02:00:00Z"))
    );
    if (surface === "user")
      await expect(root.locator(".admin-pagination-summary")).toContainText("41");
    else if (surface !== "detail")
      await expect(root.locator(".admin-list-toolbar-summary strong")).toHaveText("41");
    if (surface === "user") {
      await expect(root.locator("[data-service-id]")).toHaveAttribute(
        "data-service-id",
        service.id
      );
      await expect(root.locator(".service-id")).toContainText(service.id.slice(-8));
      await expect(root.locator(".service-id")).toHaveAttribute("title", service.id);
    } else await expect(root).toContainText(service.id);
    await expect(root).toContainText("23 GiB");
    await expect(root).toContainText(displayTime(time));
    if (surface === "customer" || surface === "detail") {
      await expect(
        root.getByRole("button", { name: fixture.label("services_manage"), exact: true })
      ).toBeDisabled();
      await expect(
        root.getByRole("button", { name: fixture.label("services_revoke"), exact: true })
      ).toBeDisabled();
      await expect(
        root.getByRole("button", { name: fixture.label("services_activate"), exact: true })
      ).toBeDisabled();
    }
    fixture.state.failure = fixture.state.detailFailure = 0;
    fixture.state.total = 53;
    fixture.state.services[0] = {
      ...service,
      used_bytes: 31 * 2 ** 30,
      last_usage_sync_at: nextTime,
    };
    fixture.state.observedAt = nextTime;
    await fixture.refresh();
    await expect(root.getByRole("alert")).toHaveCount(0);
    await expect(root).toContainText("31 GiB");
    await expect(root).toContainText(displayTime(nextTime));
    if (surface === "user")
      await expect(root.locator(".admin-pagination-summary")).toContainText("53");
    else if (surface !== "detail")
      await expect(root.locator(".admin-list-toolbar-summary strong")).toHaveText("53");
    expect(surface === "detail" ? fixture.state.detailReads : fixture.state.reads).toBe(3);
    expect(fixture.state.writes).toEqual([]);
  });

  test(`H03 ${surface}: first HTTP503 is unknown rather than a successful empty result`, async ({
    page,
  }) => {
    const fixture = await installServiceReads(page, surface);
    fixture.state.failure = fixture.state.detailFailure = 503;
    await fixture.goto();
    const root = fixture.root();
    await expect(root.getByRole("alert").first()).toContainText(
      fixture.label(surface === "user" ? "snapshot_unknown" : "services_snapshot_unknown")
    );
    await expect(root).not.toContainText(service.name);
    await expect(root).not.toContainText("0 B");
    await expect(root.locator(".admin-list-toolbar-summary")).toHaveCount(0);
    fixture.state.failure = fixture.state.detailFailure = 0;
    await fixture.refresh();
    await expect(root).toContainText(service.name);
    await expect(root.getByRole("alert")).toHaveCount(0);
  });

  for (const failure of [429, "offline"] as const) {
    test(`H02 ${surface}: ${failure} retains original values and time without writes`, async ({
      page,
    }) => {
      const fixture = await installServiceReads(page, surface);
      await fixture.goto();
      await expect(fixture.root()).toContainText(service.name);
      await page.clock.setFixedTime(new Date("2026-10-25T03:00:00Z"));
      fixture.state.failure = fixture.state.detailFailure = failure;
      await fixture.refresh();
      await expect(fixture.root().getByRole("alert").first()).toContainText(
        displayTime(surface === "global" ? time : "2026-10-25T02:00:00Z")
      );
      await expect(fixture.root()).toContainText("23 GiB");
      await expect(fixture.root().getByRole("alert").first()).not.toContainText(
        displayTime("2026-10-25T03:00:00Z")
      );
      expect(fixture.state.writes).toEqual([]);
    });
  }

  test(`H06 ${surface}: HTTP401 clears the snapshot through the existing login boundary`, async ({
    page,
  }) => {
    const fixture = await installServiceReads(page, surface);
    await fixture.goto();
    await expect(fixture.root()).toContainText(service.name);
    fixture.state.failure = fixture.state.detailFailure = 401;
    await fixture.refresh();
    await expect(page.getByText(service.name, { exact: true })).toHaveCount(0);
    await expect(page.locator(".services-screen, .admin-sidebar")).toHaveCount(0);
    expect(fixture.state.writes).toEqual([]);
  });

  if (surface !== "user") {
    test(`H07 ${surface}: HTTP403 clears target data even when fresh profile remains administrator`, async ({
      page,
    }) => {
      const fixture = await installServiceReads(page, surface);
      await fixture.goto();
      await expect(fixture.root()).toContainText(service.name);
      fixture.state.failure = fixture.state.detailFailure = 403;
      await fixture.refresh();
      await expect.poll(() => fixture.shellState.roleChecks).toBe(1);
      await expect(fixture.root()).not.toContainText(service.name);
      await expect(fixture.root()).not.toContainText(service.id);
      await expect(page.locator(".admin-sidebar")).toBeAttached();
      expect(fixture.shellState.admin).toBe(true);
      expect(fixture.state.writes).toEqual([]);
    });
  }
}

for (const surface of ["user", "customer", "global"] as const) {
  test(`H05 ${surface}: failed next page never borrows the previous page snapshot`, async ({
    page,
  }) => {
    const fixture = await installServiceReads(page, surface);
    fixture.state.total = 51;
    await fixture.goto();
    await expect(fixture.root()).toContainText(service.name);
    fixture.state.failure = 503;
    await fixture
      .root()
      .getByRole("button", {
        name: fixture.label(surface === "user" ? "next" : "services_next"),
        exact: true,
      })
      .click();
    await expect(fixture.root().getByRole("alert")).toContainText(
      fixture.label(surface === "user" ? "snapshot_unknown" : "services_snapshot_unknown")
    );
    await expect(fixture.root()).not.toContainText(service.name);
    expect(fixture.state.requests.at(-1)).toContain(
      surface === "global" ? "page=1" : `offset=${surface === "user" ? 10 : 25}`
    );
    expect(fixture.state.writes).toEqual([]);
  });

  test(`H09 ${surface}: successful empty results replace data and retain the server total`, async ({
    page,
  }) => {
    const fixture = await installServiceReads(page, surface);
    await fixture.goto();
    await expect(fixture.root()).toContainText(service.name);
    for (const total of [41, 0]) {
      fixture.state.services = [];
      fixture.state.total = total;
      await fixture.refresh();
      await expect(fixture.root()).not.toContainText(service.name);
      await expect(fixture.root().getByRole("alert")).toHaveCount(0);
      if (surface !== "user")
        await expect(fixture.root().locator(".admin-list-toolbar-summary strong")).toHaveText(
          String(total)
        );
      else if (total)
        await expect(fixture.root().locator(".admin-pagination")).toContainText(String(total));
    }
  });
}

for (const [key, value] of [
  ["q", "new-customer"],
  ["status", "paused"],
  ["sort", "usage_desc"],
  ["user_id", "43"],
]) {
  test(`H05 global: changed ${key} clears old values before a failed read`, async ({ page }) => {
    const fixture = await installServiceReads(page, "global");
    await fixture.goto();
    await expect(fixture.root()).toContainText(service.name);
    fixture.state.failure = 503;
    fixture.holdNext();
    await page.evaluate(
      ({ key, value }) => {
        const url = new URL(location.href);
        url.searchParams.set(key, value);
        history.pushState(null, "", url);
        dispatchEvent(new PopStateEvent("popstate"));
      },
      { key, value }
    );
    await expect.poll(() => fixture.state.reads).toBe(2);
    await expect(fixture.root()).not.toContainText(service.name);
    await expect(fixture.root().locator(".admin-list-toolbar-summary")).toHaveCount(0);
    fixture.release();
    await expect(fixture.root().getByRole("alert")).toContainText(
      fixture.label("services_snapshot_unknown")
    );
    expect(
      new URL(
        `http://fixture.test${fixture.state.requests.at(-1)?.replace(/^GET /, "")}`
      ).searchParams.get(key)
    ).toBe(value);
  });
}

test("H05 user: switching to catalog clears the service snapshot before HTTP503", async ({
  page,
}) => {
  const fixture = await installServiceReads(page, "user");
  await fixture.goto();
  await expect(fixture.root()).toContainText(service.name);
  fixture.state.failure = 503;
  await fixture
    .root()
    .getByRole("button", { name: fixture.copy.wa_services_catalog, exact: true })
    .click();
  await expect(fixture.root().getByRole("alert")).toContainText(
    fixture.copy.wa_services_snapshot_unknown
  );
  await expect(fixture.root()).not.toContainText(service.name);
  expect(fixture.state.requests.at(-1)).toContain("/api/service-catalog?");
});

for (const destination of ["users/43", "service-history"]) {
  test(`H04 H05 customer: navigation to ${destination} clears the previous owner's values`, async ({
    page,
  }) => {
    const fixture = await installServiceReads(page, "customer");
    await fixture.goto();
    await expect(fixture.root()).toContainText(service.name);
    fixture.state.failure = 503;
    await page.evaluate((destination) => {
      const url = new URL(location.href);
      url.pathname = `/demo/runtime/admin/${destination}`;
      history.pushState(null, "", url);
      dispatchEvent(new PopStateEvent("popstate"));
    }, destination);
    await expect(fixture.root().getByRole("alert")).toContainText(
      fixture.label("services_snapshot_unknown")
    );
    await expect(fixture.root()).not.toContainText(service.name);
    expect(fixture.state.requests.at(-1)).toContain(
      destination === "service-history" ? "deleted=true" : "user_id=43"
    );
  });
}

for (const oldFailure of [0, 503] as const) {
  test(`H10 global: a late ${oldFailure || "successful"} response cannot refill a newer query`, async ({
    page,
  }) => {
    const fixture = await installServiceReads(page, "global");
    fixture.state.failure = oldFailure;
    fixture.holdNext();
    await fixture.goto();
    await expect.poll(() => fixture.state.reads).toBe(1);
    fixture.state.failure = 0;
    fixture.state.services = [
      {
        ...service,
        id: "b".repeat(32),
        name: "HTTP independent service B",
        used_bytes: 37 * 2 ** 30,
      },
    ];
    await fixture
      .root()
      .getByRole("textbox", { name: fixture.label("console_search") })
      .fill("service B");
    await fixture
      .root()
      .getByRole("button", { name: fixture.label("search"), exact: true })
      .click();
    await expect(fixture.root()).toContainText("HTTP independent service B");
    fixture.release();
    await expect.poll(() => fixture.state.released).toBe(1);
    await expect(fixture.root()).toContainText("37 GiB");
    await expect(fixture.root()).not.toContainText(service.name);
    await expect(fixture.root().getByRole("alert")).toHaveCount(0);
  });
}

test("H08 H10 global: revocation clears data and rejects an older successful request", async ({
  page,
}) => {
  const fixture = await installServiceReads(page, "global");
  await fixture.goto();
  await expect(fixture.root()).toContainText(service.name);
  await expect(fixture.root()).toContainText("23 GiB");
  fixture.holdNext();
  await fixture.refresh();
  await expect.poll(() => fixture.state.reads).toBe(2);
  await expect(fixture.root()).toContainText(service.name);
  fixture.shellState.admin = false;
  fixture.state.failure = 403;
  await fixture
    .root()
    .getByRole("textbox", { name: fixture.label("console_search") })
    .fill("revoke");
  await fixture
    .root()
    .getByRole("button", { name: fixture.label("search"), exact: true })
    .click();
  await expect.poll(() => fixture.shellState.roleChecks).toBe(1);
  await expect(page.locator(".admin-sidebar")).toHaveCount(0);
  await expect(page.getByText(service.name, { exact: true })).toHaveCount(0);
  fixture.release();
  await expect.poll(() => fixture.state.released).toBe(1);
  await expect(page.getByText(service.name, { exact: true })).toHaveCount(0);
  await expect(page.getByRole("dialog")).toHaveCount(0);
  expect(fixture.state.writes).toEqual([]);
});

test("H10 detail: closing a pending request prevents its late result from reopening the dialog", async ({
  page,
}) => {
  const fixture = await installServiceReads(page, "global");
  await fixture.goto();
  const trigger = fixture.root().getByRole("button", { name: new RegExp(service.name) });
  await expect(trigger).toBeVisible();
  fixture.holdNext();
  await trigger.focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => fixture.state.detailReads).toBe(1);
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  fixture.release();
  await expect.poll(() => fixture.state.released).toBe(1);
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(trigger).toBeFocused();
});

test("H04 H10 detail: changing service ID clears the old record and ignores its late response", async ({
  page,
}) => {
  const fixture = await installServiceReads(page, "detail");
  await fixture.goto();
  await expect(fixture.root()).toContainText(service.name);
  fixture.holdNext();
  await fixture.refresh();
  await expect.poll(() => fixture.state.detailReads).toBe(2);
  fixture.state.detailFailure = 503;
  await page.evaluate(() => {
    const url = new URL(location.href);
    url.searchParams.set("service_id", "b".repeat(32));
    history.pushState(null, "", url);
    dispatchEvent(new PopStateEvent("popstate"));
  });
  await expect(fixture.root().getByRole("alert")).toContainText(
    fixture.label("services_snapshot_unknown")
  );
  await expect(fixture.root()).not.toContainText(service.name);
  fixture.release();
  await expect.poll(() => fixture.state.released).toBe(1);
  await expect(fixture.root()).not.toContainText(service.id);
  await expect(fixture.root().getByRole("alert")).toBeVisible();
});

test("H10 user: closing pending HTTP detail keeps it closed after the response completes", async ({
  page,
}) => {
  const fixture = await installServiceReads(page, "user");
  await fixture.goto();
  const trigger = fixture
    .root()
    .getByRole("button", { name: fixture.copy.wa_services_details, exact: true });
  await expect(trigger).toBeVisible();
  fixture.holdNext();
  await trigger.focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => fixture.state.detailReads).toBe(1);
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  fixture.release();
  await expect.poll(() => fixture.state.released).toBe(1);
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(trigger).toBeFocused();
});

test("H11 user detail: a reentrant same-service read hides the old subscription on HTTP503", async ({
  page,
}) => {
  const fixture = await installServiceReads(page, "user");
  await fixture.goto();
  const trigger = fixture
    .root()
    .getByRole("button", { name: fixture.copy.wa_services_details, exact: true });
  await trigger.click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("23 GiB");
  await dialog
    .locator(".service-subscription")
    .getByRole("button", { name: fixture.copy.wa_services_subscription, exact: true })
    .click();
  await expect(
    dialog.getByRole("textbox", { name: fixture.copy.wa_services_subscription })
  ).toHaveValue("https://subscription.example.test/private-service-a");
  await page.clock.setFixedTime(new Date("2026-10-25T03:00:00Z"));
  fixture.state.detailFailure = 503;
  // Re-enter the existing handler to check its invariant; this is not a reachable manual refresh gesture.
  await trigger.dispatchEvent("click");
  await expect(dialog.getByRole("alert")).toContainText(displayTime("2026-10-25T02:00:00Z"));
  await expect(dialog).toContainText("23 GiB");
  await expect(dialog.locator(".service-subscription")).toHaveCount(0);
  await expect(
    dialog.getByRole("textbox", { name: fixture.copy.wa_services_subscription })
  ).toHaveCount(0);
  await expect(dialog.locator("[data-service-next-step]")).toHaveCount(0);
  await expect(dialog).not.toContainText("private-service-a");
  expect(fixture.state.subscriptionReads).toBe(1);
  expect(fixture.state.detailReads).toBe(2);
  expect(fixture.state.writes).toEqual([]);
});

for (const surface of ["user", "global"] as const) {
  test(`H04 H10 ${surface}: logout and email login isolate the next account with the same app client`, async ({
    page,
  }) => {
    const fixture = await installServiceReads(page, surface);
    if (surface === "global")
      await page.addInitScript(() => {
        type Props = { api: unknown };
        type Bundle = { mount: (target: HTMLElement, props: Props) => unknown };
        let bundle: Bundle | undefined;
        let firstApi: unknown;
        let mounts = 0;
        Object.defineProperty(window, "SubscriptionWebAppAdmin", {
          configurable: true,
          get: () => bundle,
          set(value: Bundle) {
            const mount = value.mount;
            value.mount = (target, props) => {
              firstApi ??= props.api;
              document.documentElement.dataset.serviceApiStable = String(firstApi === props.api);
              document.documentElement.dataset.serviceApiMounts = String(++mounts);
              return mount(target, props);
            };
            bundle = value;
          },
        });
      });
    await fixture.goto();
    const origin = await page.evaluate(() => performance.timeOrigin);
    await expect(fixture.root()).toContainText(service.name);
    fixture.holdNext();
    await fixture.refresh();
    await expect.poll(() => fixture.state.reads).toBe(2);
    if (surface === "global")
      await page
        .locator(".admin-sidebar")
        .getByRole("button", { name: fixture.label("exit"), exact: true })
        .click();
    await page
      .locator("nav.bottom-nav")
      .getByRole("button", { name: fixture.copy.wa_nav_settings, exact: true })
      .click();
    await page.locator(".settings-row-logout").click();
    await expect(page.locator(".auth-screen")).toBeVisible();
    await expect(page.getByText(service.name, { exact: true })).toHaveCount(0);
    fixture.state.accountId = 43;
    fixture.state.services = [
      {
        ...service,
        id: "b".repeat(32),
        user_id: 43,
        name: "HTTP account B service",
        used_bytes: 37 * 2 ** 30,
      },
    ];
    fixture.state.failure = 503;
    await page
      .getByPlaceholder(fixture.copy.wa_email_placeholder, { exact: true })
      .fill("account-43@example.test");
    await page.getByRole("button", { name: fixture.copy.wa_send_code_email, exact: true }).click();
    await page
      .getByRole("textbox", { name: fixture.copy.wa_email_code_aria, exact: true })
      .fill("123456");
    await expect(page.locator(".auth-screen")).toHaveCount(0);
    if (surface === "global") {
      await page
        .locator("nav.bottom-nav")
        .getByRole("button", { name: fixture.copy.wa_nav_admin, exact: true })
        .click();
      await page.locator('[data-admin-section="services"]').click();
      await expect(page.locator("html")).toHaveAttribute("data-service-api-stable", "true");
      expect(
        Number(await page.locator("html").getAttribute("data-service-api-mounts"))
      ).toBeGreaterThan(1);
    } else
      await page
        .locator("nav.bottom-nav")
        .getByRole("button", { name: fixture.copy.wa_services_nav, exact: true })
        .click();
    await expect(fixture.root().getByRole("alert")).toContainText(
      fixture.label(surface === "user" ? "snapshot_unknown" : "services_snapshot_unknown")
    );
    await expect(fixture.root()).not.toContainText(service.name);
    await expect(fixture.root()).not.toContainText(service.id);
    fixture.state.failure = 0;
    await fixture.refresh();
    await expect(fixture.root()).toContainText("HTTP account B service");
    fixture.release();
    await expect.poll(() => fixture.state.released).toBe(1);
    await expect(fixture.root()).toContainText("HTTP account B service");
    await expect(fixture.root()).not.toContainText(service.name);
    await expect(fixture.root()).not.toContainText(service.id);
    await expect(fixture.root().getByRole("alert")).toHaveCount(0);
    expect(await page.evaluate(() => performance.timeOrigin)).toBe(origin);
    expect(fixture.state.authRequests).toEqual([
      "/api/auth/logout",
      "/api/auth/email/request",
      "/api/auth/email/verify",
    ]);
    expect(fixture.state.writes).toEqual([]);
  });
}

for (const width of [1440, 390]) {
  for (const surface of ["global", "customer"] as const) {
    test(`F03 ${surface}: successful detail then HTTP503 retains data and restores focus at ${width}`, async ({
      page,
    }) => {
      await page.setViewportSize({ width, height: 1000 });
      const fixture = await installServiceReads(page, surface);
      await fixture.goto();
      if (surface === "customer")
        await fixture.root().locator(":scope > details > summary").click();
      const trigger = fixture.root().getByRole("button", {
        name:
          surface === "global" ? new RegExp(service.name) : fixture.label("console_service_detail"),
        exact: surface === "customer",
      });
      await trigger.focus();
      await page.keyboard.press("Enter");
      const detail = page.locator(".console-service-detail");
      await expect(detail).toContainText(service.name);
      await expect(detail).toContainText("23 GiB");
      fixture.state.detailFailure = 503;
      await page.clock.setFixedTime(new Date("2026-10-25T03:00:00Z"));
      await detail
        .getByRole("button", { name: fixture.label("refresh"), exact: true })
        .first()
        .click();
      await expect(detail.getByRole("alert")).toContainText(displayTime("2026-10-25T02:00:00Z"));
      await expect(detail).toContainText(service.name);
      await expect(detail).toContainText("23 GiB");
      await page.keyboard.press("Escape");
      await expect(page.getByRole("dialog")).toHaveCount(0);
      if (surface === "global") await expect(trigger).toBeFocused();
      else
        await expect(
          page
            .locator(".console-services")
            .getByRole("textbox", { name: fixture.label("console_search") })
        ).toBeFocused();
      expect(fixture.state.detailReads).toBe(2);
      expect(fixture.state.writes).toEqual([]);
    });
  }

  for (const retry of [false, true]) {
    test(`F01 F03 global keyboard entry ${retry ? "HTTP503 retry" : "success"} restores original focus at ${width}`, async ({
      page,
    }) => {
      await page.setViewportSize({ width, height: 1000 });
      const fixture = await installServiceReads(page, "global");
      fixture.state.detailFailure = retry ? 503 : 0;
      await fixture.goto();
      const trigger = fixture.root().getByRole("button", { name: new RegExp(service.name) });
      await trigger.focus();
      await page.keyboard.press("Enter");
      const dialog = page.getByRole("dialog", {
        name: fixture.label("console_service_detail"),
        exact: true,
      });
      await expect(dialog).toBeVisible();
      if (retry) {
        await expect(dialog.getByRole("alert")).toContainText(
          fixture.label("console_detail_failed")
        );
        fixture.state.detailFailure = 0;
        await dialog.getByRole("button", { name: fixture.label("refresh"), exact: true }).focus();
        await page.keyboard.press("Enter");
      }
      await expect(dialog).toContainText(service.name);
      await page.keyboard.press("Escape");
      await expect(dialog).toHaveCount(0);
      await expect(trigger).toBeFocused();
      await expect(page).not.toHaveURL(/service_id=/);
      expect(fixture.state.detailReads).toBe(retry ? 2 : 1);
    });
  }

  test(`F02 F03 customer keyboard navigation uses current-list fallback after its entry unmounts at ${width}`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 1000 });
    const fixture = await installServiceReads(page, "customer");
    fixture.state.detailFailure = 503;
    await fixture.goto();
    await fixture.root().locator(":scope > details > summary").click();
    const trigger = fixture
      .root()
      .getByRole("button", { name: fixture.label("console_service_detail"), exact: true });
    await trigger.focus();
    await page.keyboard.press("Enter");
    const dialog = page.getByRole("dialog", {
      name: fixture.label("console_service_detail"),
      exact: true,
    });
    await expect(dialog.getByRole("alert")).toContainText(fixture.label("console_detail_failed"));
    await expect(trigger).toHaveCount(0);
    fixture.state.detailFailure = 0;
    await dialog.getByRole("button", { name: fixture.label("refresh"), exact: true }).focus();
    await page.keyboard.press("Enter");
    await expect(dialog).toContainText(service.name);
    await page.keyboard.press("Escape");
    await expect(dialog).toHaveCount(0);
    await expect(
      page
        .locator(".console-services")
        .getByRole("textbox", { name: fixture.label("console_search") })
    ).toBeFocused();
    expect(fixture.state.detailReads).toBe(2);
  });
}

for (const failure of [0, 503] as const) {
  test(`F04 direct detail ${failure || "success"} closes to the existing search control`, async ({
    page,
  }) => {
    const fixture = await installServiceReads(page, "detail");
    fixture.state.detailFailure = failure;
    await fixture.goto();
    await expect(fixture.root()).toBeVisible();
    await expect(fixture.root()).toContainText(
      failure ? fixture.label("console_detail_failed") : service.name
    );
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(
      page
        .locator(".console-services")
        .getByRole("textbox", { name: fixture.label("console_search") })
    ).toBeFocused();
  });
}

test("F04 H05 filtering away an open detail returns focus to the current search", async ({
  page,
}) => {
  const fixture = await installServiceReads(page, "detail");
  await fixture.goto();
  await expect(fixture.root()).toContainText(service.name);
  await page.evaluate(() => {
    const url = new URL(location.href);
    url.searchParams.set("q", "other-service");
    history.pushState(null, "", url);
    dispatchEvent(new PopStateEvent("popstate"));
  });
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(
    page
      .locator(".console-services")
      .getByRole("textbox", { name: fixture.label("console_search") })
  ).toBeFocused();
});

for (const language of ["en", "ru", "zh-hans"]) {
  for (const surface of ["user", "global"] as const) {
    test(`H01 snapshot notice readability ${surface} ${language} at 390`, async ({
      page,
    }, info) => {
      await page.setViewportSize({ width: 390, height: 1000 });
      const fixture = await installServiceReads(page, surface, language);
      await fixture.goto();
      await expect(fixture.root()).toContainText(service.name);
      fixture.state.failure = 503;
      await fixture.refresh();
      const alert = fixture.root().getByRole("alert").first();
      await expect(alert).toContainText(
        displayTime(surface === "global" ? time : "2026-10-25T02:00:00Z")
      );
      await alert.scrollIntoViewIfNeeded();
      expect(await alert.evaluate((node) => node.scrollWidth <= node.clientWidth + 1)).toBe(true);
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 2)
      ).toBe(true);
      await page.screenshot({
        path: info.outputPath("http-stale-snapshot.png"),
        animations: "disabled",
      });
    });
  }
}
