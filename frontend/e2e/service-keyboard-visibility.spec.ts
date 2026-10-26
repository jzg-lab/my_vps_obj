import { expect, test, type Page } from "@playwright/test";
import { installServiceReads, service } from "./fixtures/service-reads";

// Hit testing checks actual exposure, including fixed overlays that toBeVisible misses.
async function sample(page: Page) {
  return page.evaluate(() => {
    const element = document.activeElement;
    if (!(element instanceof HTMLElement) || element === document.body) return null;
    const rect = element.getBoundingClientRect();
    const left = Math.max(0, rect.left);
    const right = Math.min(innerWidth, rect.right);
    const top = Math.max(0, rect.top);
    const bottom = Math.min(innerHeight, rect.bottom);
    let exposed = 0;
    if (right > left && bottom > top) {
      for (const x of [0.1, 0.3, 0.5, 0.7, 0.9]) {
        for (const y of [0.1, 0.3, 0.5, 0.7, 0.9]) {
          const hit = document.elementFromPoint(
            left + (right - left) * x,
            top + (bottom - top) * y
          );
          if (hit && (element === hit || element.contains(hit))) exposed++;
        }
      }
    }
    const geometry = (node: Element) => {
      const r = node.getBoundingClientRect();
      return { x: r.x, y: r.y, width: r.width, height: r.height };
    };
    return {
      label: element.getAttribute("aria-label") || element.textContent?.trim(),
      serviceId: element.closest("[data-service-id]")?.getAttribute("data-service-id"),
      exposed,
      focusVisible: element.matches(":focus-visible"),
      rect: geometry(element),
      scrollY,
      navigation: Array.from(document.querySelectorAll(".bottom-nav")).map(geometry),
      containers: [document.scrollingElement, document.querySelector(".phone-screen")]
        .filter((node): node is Element => node !== null)
        .map((node) => ({
          tag: node.tagName,
          class: node.getAttribute("class"),
          scrollTop: node.scrollTop,
          clientHeight: node.clientHeight,
          scrollHeight: node.scrollHeight,
          overflow: getComputedStyle(node).overflow,
          scrollPaddingBottom: getComputedStyle(node).scrollPaddingBottom,
        })),
    };
  });
}

async function visibleFocus(page: Page, phase: string, evidence: unknown[]) {
  evidence.push({ phase, initial: await sample(page) });
  await expect
    .poll(async () => (await sample(page))?.exposed || 0, {
      message: `${phase}: keyboard focus has an exposed sampled point`,
      timeout: 1500,
    })
    .toBeGreaterThan(0);
  const settled = await sample(page);
  evidence.push({ phase, settled });
  expect(settled?.focusVisible, `${phase}: visible keyboard focus`).toBe(true);
}

for (const language of ["en", "zh-hans"]) {
  for (const width of [320, 390, 800, 1023, 1024, 1440]) {
    test(`services ${language} ${width}: Tab exposes four services in normal and HTTP503 states`, async ({
      page,
    }, info) => {
      await page.setViewportSize({ width, height: width < 500 ? 640 : 900 });
      const fixture = await installServiceReads(page, "user", language);
      fixture.state.services = [
        service,
        ...["b", "c", "d"].map((key, index) => ({
          ...service,
          id: key.repeat(32),
          name: `SYNTHETIC independent service ${key.toUpperCase()}`,
          quota_bytes: (index + 2) * 100 * 2 ** 30,
        })),
      ];
      fixture.state.total = 4;
      const evidence: unknown[] = [];
      try {
        await page.goto("/demo/runtime/settings?mock=services&theme_preview=dark");
        const navigation = page
          .locator("nav")
          .getByRole("button", { name: fixture.copy.wa_services_nav, exact: true });
        await navigation.focus();
        await page.keyboard.press("Enter");
        const root = fixture.root();
        await expect(root.locator("[data-service-id]")).toHaveCount(4);
        const refresh = root.getByRole("button", { name: fixture.label("refresh"), exact: true });
        for (const phase of ["normal", "retained-http503"]) {
          if (phase === "retained-http503") {
            fixture.state.failure = 503;
            await refresh.focus();
            await page.keyboard.press("Enter");
            await expect(root.getByRole("alert")).toBeVisible();
            await expect(root.locator("[data-service-id]")).toHaveCount(4);
          }
          await refresh.focus();
          const seen: string[] = [];
          for (let step = 0; step < 16 && seen.length < 4; step++) {
            await page.keyboard.press("Tab");
            const current = await sample(page);
            await visibleFocus(page, `${phase}-${step}`, evidence);
            if (current?.serviceId && current.label === fixture.copy.wa_services_details)
              seen.push(current.serviceId);
          }
          expect(seen).toEqual(fixture.state.services.map(({ id }) => id));
          await info.attach(phase, { body: await page.screenshot(), contentType: "image/png" });
          if (phase === "normal") {
            const trigger = root
              .locator(`[data-service-id="${service.id}"]`)
              .getByRole("button", { name: fixture.copy.wa_services_details, exact: true });
            for (let step = 0; step < 16; step++) {
              if (await trigger.evaluate((node) => node === document.activeElement)) break;
              await page.keyboard.press("Shift+Tab");
              await visibleFocus(page, `return-to-detail-${step}`, evidence);
            }
            await expect(trigger).toBeFocused();
            await page.keyboard.press("Enter");
            const dialog = page.getByRole("dialog");
            await expect(dialog).toContainText(service.name);
            const subscription = dialog.getByRole("button", {
              name: fixture.copy.wa_services_subscription,
              exact: true,
            });
            await expect(subscription).toBeVisible();
            for (let step = 0; step < 8; step++) {
              if (await subscription.evaluate((node) => node === document.activeElement)) break;
              await page.keyboard.press("Tab");
              await visibleFocus(page, `detail-entry-${step}`, evidence);
            }
            await expect(subscription).toBeFocused();
            await visibleFocus(page, "detail-subscription", evidence);
            await page.keyboard.press("Enter");
            await expect.poll(() => fixture.state.subscriptionReads).toBeGreaterThan(0);
            await expect(
              dialog.getByRole("textbox", { name: fixture.copy.wa_services_subscription })
            ).toHaveValue("https://subscription.example.test/private-service-a");
            for (let step = 0; step < 6; step++) {
              await page.keyboard.press("Tab");
              await expect(dialog.locator(":focus")).toHaveCount(1);
              await visibleFocus(page, `detail-dialog-${step}`, evidence);
            }
            await info.attach("detail-dialog", {
              body: await page.screenshot(),
              contentType: "image/png",
            });
            await page.keyboard.press("Escape");
            await expect(dialog).toHaveCount(0);
            await expect(trigger).toBeFocused();
          }
        }
        expect(fixture.state.writes).toEqual([]);
        expect(fixture.state.pageErrors).toEqual([]);
      } finally {
        await info.attach("keyboard-geometry-http", {
          body: JSON.stringify({ evidence, state: fixture.state }, null, 2),
          contentType: "application/json",
        });
        await info.attach("final-state", {
          body: await page.screenshot(),
          contentType: "image/png",
        });
      }
    });
  }

  for (const width of [390, 1440]) {
    test(`settings ${language} ${width}: language menu keyboard, Escape and return focus`, async ({
      page,
    }, info) => {
      await page.setViewportSize({ width, height: width < 500 ? 640 : 900 });
      const fixture = await installServiceReads(page, "user", language);
      const evidence: unknown[] = [];
      try {
        await page.goto("/demo/runtime/settings?mock=services&theme_preview=dark");
        const main = page.locator(".phone-screen > main.content.with-nav");
        const trigger = main.locator(
          ".settings-row-language:not(.settings-row-theme) .language-select-trigger"
        );
        await expect(trigger).toBeVisible();
        await main.locator("button").first().focus();
        for (let step = 0; step < 30; step++) {
          if (await trigger.evaluate((node) => node === document.activeElement)) break;
          await page.keyboard.press("Tab");
          await visibleFocus(page, `settings-${step}`, evidence);
        }
        await expect(trigger).toBeFocused();
        await page.keyboard.press("Enter");
        const menu = page.getByRole("listbox");
        await expect(menu).toBeVisible();
        await page.keyboard.press("ArrowDown");
        await expect(menu.getByRole("option").first()).toBeVisible();
        await info.attach("open-language-menu", {
          body: await page.screenshot(),
          contentType: "image/png",
        });
        await page.keyboard.press("Escape");
        await expect(menu).toHaveCount(0);
        await expect(trigger).toBeFocused();
        await visibleFocus(page, "settings-menu-return", evidence);
        expect(fixture.state.writes).toEqual([]);
        expect(fixture.state.pageErrors).toEqual([]);
      } finally {
        await info.attach("settings-geometry-http", {
          body: JSON.stringify({ evidence, state: fixture.state }, null, 2),
          contentType: "application/json",
        });
        await info.attach("final-state", {
          body: await page.screenshot(),
          contentType: "image/png",
        });
      }
    });
  }
}
