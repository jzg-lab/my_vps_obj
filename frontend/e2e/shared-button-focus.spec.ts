import { expect, test } from "@playwright/test";
import { installServiceReads } from "./fixtures/service-reads";

for (const width of [320, 1440]) {
  for (const consumer of ["services", "gift"] as const) {
    test(`shared Button keeps its keyboard ring while hovered: ${consumer} ${width}`, async ({
      page,
    }, info) => {
      await page.setViewportSize({ width, height: 900 });
      const errors: string[] = [];
      page.on("pageerror", (error) => errors.push(error.message));
      const fixture =
        consumer === "services" ? await installServiceReads(page, "user", "zh-hans") : null;
      const target = page.locator(
        consumer === "services"
          ? '.services-tabs > button[aria-pressed="true"]'
          : ".gift-entry .gift-intro > button"
      );
      const observe = () =>
        target.evaluate((node) => {
          const style = getComputedStyle(node),
            rect = node.getBoundingClientRect();
          const hit = document.elementFromPoint(rect.x + rect.width / 2, rect.y + rect.height / 2);
          const ancestors: Element[] = [];
          for (let current: Element | null = node; current; current = current.parentElement)
            ancestors.push(current);
          const chain = ancestors.map((element) => {
            const r = element.getBoundingClientRect(),
              computed = getComputedStyle(element);
            return {
              tag: element.tagName,
              class: element.getAttribute("class"),
              opacity: computed.opacity,
              backgroundColor: computed.backgroundColor,
              backgroundImage: computed.backgroundImage,
              color: computed.color,
              border: computed.border,
              rect: { x: r.x, y: r.y, width: r.width, height: r.height },
              animations: element
                .getAnimations()
                .map((a) => ({ playState: a.playState, pending: a.pending })),
            };
          });
          return {
            focused: node === document.activeElement,
            focusVisible: node.matches(":focus-visible"),
            hovered: node.matches(":hover"),
            enabled: !node.matches(":disabled"),
            exposed: Boolean(hit && (hit === node || node.contains(hit))),
            boxShadow: style.boxShadow,
            outline: style.outline,
            backgroundColor: style.backgroundColor,
            backgroundImage: style.backgroundImage,
            color: style.color,
            border: style.border,
            ring: / 0px 0px 0px 3px(?:,|$)/.test(style.boxShadow),
            settled: chain.every(
              (entry) =>
                entry.opacity === "1" &&
                entry.animations.every((a) => a.playState === "finished" && !a.pending)
            ),
            chain,
          };
        });
      const observations: { observedAt: string; state: Awaited<ReturnType<typeof observe>> }[] = [];
      try {
        if (fixture) await fixture.goto();
        else
          await page.goto(
            "/demo/runtime/app/?mock=checkout-addons&path=/invite&gift_demo=empty&theme_preview=dark"
          );
        await expect(target).toBeVisible();
        await expect(target).toBeEnabled();
        await target.focus();
        await page.keyboard.press("Shift+Tab");
        await expect(target).not.toBeFocused();
        await target.hover();
        await page.keyboard.press("Tab");
        await expect(target).toBeFocused();
        await expect
          .poll(async () => {
            const state = await observe();
            observations.push({ observedAt: new Date().toISOString(), state });
            return (
              state.focused &&
              state.focusVisible &&
              state.hovered &&
              state.enabled &&
              state.exposed &&
              state.ring &&
              state.settled
            );
          })
          .toBe(true);
        expect(errors).toEqual([]);
        if (fixture) expect(fixture.state.writes).toEqual([]);
      } finally {
        await info.attach("hover-keyboard-focus-computed", {
          body: JSON.stringify({ consumer, width, observations, errors }, null, 2),
          contentType: "application/json",
        });
        await info.attach("hover-keyboard-focus-screenshot", {
          body: await page.screenshot(),
          contentType: "image/png",
        });
      }
    });
  }
}
