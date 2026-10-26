import { expect, test, type Locator, type Page } from "@playwright/test";
import { installServiceReads, service } from "./fixtures/service-reads";

async function sampleFocus(page: Page) {
  return page.evaluate(() => {
    const element = document.activeElement;
    if (!(element instanceof HTMLElement) || element === document.body) return null;
    const rect = element.getBoundingClientRect();
    const left = Math.max(0, rect.left);
    const right = Math.min(innerWidth, rect.right);
    const top = Math.max(0, rect.top);
    const bottom = Math.min(innerHeight, rect.bottom);
    let exposed = false;
    if (right > left && bottom > top) {
      for (const x of [0.1, 0.5, 0.9]) {
        for (const y of [0.1, 0.5, 0.9]) {
          const hit = document.elementFromPoint(
            left + (right - left) * x,
            top + (bottom - top) * y
          );
          if (hit && (element === hit || element.contains(hit))) exposed = true;
        }
      }
    }
    return {
      label: element.getAttribute("aria-label") || element.textContent?.trim(),
      insideSidebar: Boolean(element.closest(".admin-sidebar")),
      insideContent: Boolean(element.closest(".admin-content")),
      inert: Boolean(element.closest("[inert]")),
      exposed,
      rect: { x: rect.x, y: rect.y, width: rect.width, height: rect.height },
    };
  });
}

async function exposedFocus(page: Page, phase: string, evidence: unknown[]) {
  evidence.push({ phase, initial: await sampleFocus(page) });
  await expect
    .poll(async () => (await sampleFocus(page))?.exposed, {
      message: `${phase}: focus is exposed, not covered by the sidebar or backdrop`,
    })
    .toBe(true);
  const current = await sampleFocus(page);
  evidence.push({ phase, ...current });
  expect(current?.inert, `${phase}: focus is not inert`).toBe(false);
  return current;
}

async function tabTo(page: Page, target: Locator, phase: string, evidence: unknown[]) {
  for (let step = 0; step < 80; step++) {
    if (await target.evaluate((element) => element === document.activeElement)) return;
    await page.keyboard.press("Tab");
    await exposedFocus(page, `${phase}-${step}`, evidence);
  }
  await expect(target).toBeFocused();
}

for (const surface of ["customer", "global"] as const) {
  for (const width of [320, 390, 900, 1023]) {
    test(`${surface} sidebar excludes hidden controls and restores keyboard access at ${width}px`, async ({
      page,
    }, info) => {
      await page.setViewportSize({ width, height: 900 });
      const fixture = await installServiceReads(page, surface, "zh-hans");
      await fixture.goto();
      await expect(fixture.root()).toContainText(service.name);
      const sidebar = page.locator(".admin-sidebar");
      const toggle = page.locator(".admin-mobile-toggle");
      const exit = sidebar.locator(".admin-sidebar-brand button");
      const group = sidebar.locator("[data-admin-nav-group]").first();

      await expect(toggle).toHaveAttribute("aria-expanded", "false");
      await expect(page.getByRole("dialog")).toHaveCount(0);
      await toggle.focus();
      await page.keyboard.press("Shift+Tab");
      expect(await sidebar.evaluate((element) => element.contains(document.activeElement))).toBe(
        false
      );
      await exit.evaluate((element) => (element as HTMLElement).focus());
      await expect(exit).not.toBeFocused();

      await toggle.focus();
      await page.keyboard.press("Enter");
      await expect(toggle).toHaveAttribute("aria-expanded", "true");
      await expect(page.getByRole("dialog")).toHaveCount(1);
      await expect(sidebar).toHaveAttribute("role", "dialog");
      await expect(sidebar).toHaveCSS("transform", "matrix(1, 0, 0, 1, 0, 0)");
      await expect(exit).toBeFocused();
      await page.keyboard.press("Tab");
      await expect(group).toBeFocused();
      await group.press("Enter");
      await expect(group).toHaveAttribute("aria-expanded", "false");
      await group.press("Enter");
      await expect(group).toHaveAttribute("aria-expanded", "true");
      await page.screenshot({ path: info.outputPath("sidebar-open.png") });
      await page.keyboard.press("Escape");
      await expect(toggle).toHaveAttribute("aria-expanded", "false");
      await expect(page.getByRole("dialog")).toHaveCount(0);
      await expect(toggle).toBeFocused();
      await page.keyboard.press("Shift+Tab");
      expect(await sidebar.evaluate((element) => element.contains(document.activeElement))).toBe(
        false
      );

      // The drawer boundary is 1023px, independently of the language menu's 720px.
      await page.setViewportSize({ width: 1024, height: 900 });
      await expect
        .poll(() => sidebar.evaluate((element: HTMLElement) => element.inert))
        .toBe(false);
      await exit.focus();
      await expect(exit).toBeFocused();
      await page.keyboard.press("Tab");
      await expect(group).toBeFocused();
      await expect(sidebar).toHaveCSS("transform", "none");
      await expect(page.getByRole("dialog")).toHaveCount(0);
      await page.screenshot({ path: info.outputPath("sidebar-desktop.png") });
      await page.setViewportSize({ width, height: 900 });
      await expect.poll(() => sidebar.evaluate((element: HTMLElement) => element.inert)).toBe(true);
      await expect(toggle).toBeFocused();
      await page.keyboard.press("Shift+Tab");
      expect(await sidebar.evaluate((element) => element.contains(document.activeElement))).toBe(
        false
      );
      await expect(sidebar).toHaveCSS("transform", "matrix(1, 0, 0, 1, -280, 0)");
      await expect(page.getByRole("dialog")).toHaveCount(0);
      await page.screenshot({ path: info.outputPath("sidebar-closed.png") });
      expect(fixture.state.writes).toEqual([]);
      expect(fixture.state.pageErrors).toEqual([]);
    });
  }

  for (const width of [320, 1023]) {
    test(`${surface} open sidebar keeps sequential keyboard focus exposed at ${width}px`, async ({
      page,
    }, info) => {
      await page.setViewportSize({ width, height: 900 });
      const fixture = await installServiceReads(page, surface, "zh-hans");
      const evidence: unknown[] = [];
      try {
        await fixture.goto();
        await expect(fixture.root()).toContainText(service.name);
        const sidebar = page.locator(".admin-sidebar");
        const content = page.locator(".admin-content");
        const toggle = page.locator(".admin-mobile-toggle");
        const exit = sidebar.locator(".admin-sidebar-brand button");
        const footer = sidebar.locator(".admin-version-link");
        const language = sidebar.locator(".admin-language-trigger");
        const navigation = sidebar.locator('[data-admin-section="services"]');
        await toggle.focus();
        await page.keyboard.press("Enter");
        await expect(toggle).toHaveAttribute("aria-expanded", "true");
        await expect(sidebar).toHaveCSS("transform", "matrix(1, 0, 0, 1, 0, 0)");
        await expect(exit).toBeFocused();
        await expect
          .poll(() => content.evaluate((element: HTMLElement) => element.inert))
          .toBe(true);
        await exposedFocus(page, "opened", evidence);

        // Traverse through both ends without refocusing or clicking a drawer control.
        for (const key of ["Tab", "Shift+Tab"]) {
          let reachedFooter = false;
          for (let step = 0; step < 80; step++) {
            await page.keyboard.press(key);
            const current = await exposedFocus(page, `${key}-${step}`, evidence);
            expect(current?.insideSidebar).toBe(true);
            if (await footer.evaluate((element) => element === document.activeElement))
              reachedFooter = true;
            if (await exit.evaluate((element) => element === document.activeElement)) break;
          }
          expect(reachedFooter, `${key}: traverses the footer before wrapping`).toBe(true);
          await expect(exit).toBeFocused();
        }
        await page.screenshot({ path: info.outputPath("sidebar-keyboard-cycle.png") });

        await tabTo(page, language, "language", evidence);
        await page.keyboard.press("Enter");
        await expect(page.getByRole("listbox")).toBeVisible();
        await page.keyboard.press("Escape");
        await expect(page.getByRole("listbox")).toHaveCount(0);
        await expect(language).toBeFocused();
        await expect(toggle).toHaveAttribute("aria-expanded", "true");
        await exposedFocus(page, "language-return", evidence);
        await page.keyboard.press("Escape");
        await expect(toggle).toHaveAttribute("aria-expanded", "false");
        await expect(toggle).toBeFocused();
        await exposedFocus(page, "escape-return", evidence);
        await expect(page.getByRole("dialog")).toHaveCount(0);

        await page.keyboard.press("Enter");
        await expect(exit).toBeFocused();
        await page.locator(".admin-sidebar-backdrop").click({
          position: { x: width - 8, y: 450 },
        });
        await expect(toggle).toHaveAttribute("aria-expanded", "false");
        await expect(toggle).toBeFocused();
        await exposedFocus(page, "backdrop-return", evidence);
        await expect(page.getByRole("dialog")).toHaveCount(0);

        await page.keyboard.press("Enter");
        await expect(exit).toBeFocused();
        await tabTo(page, navigation, "navigation", evidence);
        await page.keyboard.press("Enter");
        await expect(toggle).toHaveAttribute("aria-expanded", "false");
        await expect(toggle).toBeFocused();
        await expect(page.locator('[data-admin-active-section="services"]')).toBeVisible();
        await exposedFocus(page, "navigation-return", evidence);
        await expect(page.getByRole("dialog")).toHaveCount(0);

        await page.keyboard.press("Enter");
        await expect(exit).toBeFocused();
        await page.setViewportSize({ width: 1024, height: 900 });
        await expect(toggle).toHaveAttribute("aria-expanded", "false");
        await expect(sidebar).toHaveCSS("transform", "none");
        await expect
          .poll(() => content.evaluate((element: HTMLElement) => element.inert))
          .toBe(false);
        await expect(exit).toBeFocused();
        await exposedFocus(page, "desktop-resize", evidence);
        await tabTo(page, footer, "desktop-navigation", evidence);
        await page.keyboard.press("Tab");
        expect((await exposedFocus(page, "desktop-content", evidence))?.insideContent).toBe(true);
        await page.keyboard.press("Shift+Tab");
        await expect(footer).toBeFocused();
        await page.setViewportSize({ width, height: 900 });
        await expect
          .poll(() => sidebar.evaluate((element: HTMLElement) => element.inert))
          .toBe(true);
        await expect(toggle).toBeFocused();
        await exposedFocus(page, "mobile-resize-return", evidence);
        await page.keyboard.press("Tab");
        const current = await exposedFocus(page, "mobile-content", evidence);
        expect(current?.insideSidebar).toBe(false);
        expect(current?.insideContent).toBe(true);
        expect(fixture.state.writes).toEqual([]);
        expect(fixture.state.pageErrors).toEqual([]);
      } finally {
        await info.attach("sidebar-keyboard-exposure", {
          body: JSON.stringify({
            evidence,
            writes: fixture.state.writes,
            pageErrors: fixture.state.pageErrors,
          }),
          contentType: "application/json",
        });
        await info.attach("sidebar-final", {
          body: await page.screenshot(),
          contentType: "image/png",
        });
      }
    });
  }
}
