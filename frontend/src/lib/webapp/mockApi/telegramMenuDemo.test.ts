import { describe, expect, it } from "vitest";
import { telegramMenuDemoResponse } from "./telegramMenuDemo";

describe("Telegram menu preview languages", () => {
  it("keeps Chinese labels and retains Russian as a selectable language", () => {
    const config = telegramMenuDemoResponse("/admin/telegram-menu", {}, "zh-hans") as {
      languages: { code: string }[];
      buttons: { label: string }[];
    };
    expect(config.languages.map((item) => item.code)).toEqual(["ru", "en", "zh-hans"]);
    expect(config.buttons.map((item) => item.label).join(" ")).toContain("个人中心");
    expect(config.buttons.map((item) => item.label).join(" ")).not.toMatch(/[А-Яа-яЁё]/);
    const preview = telegramMenuDemoResponse(
      "/admin/telegram-menu/preview",
      {
        method: "POST",
        body: JSON.stringify({
          screen: "main",
          scenario: "active",
          appearance: { schema_version: 1, buttons: {} },
        }),
      },
      "zh-hans"
    );
    expect(JSON.stringify(preview)).toContain("个人中心");
    expect(JSON.stringify(preview)).not.toMatch(/[А-Яа-яЁё]/);
  });
});
