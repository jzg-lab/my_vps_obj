import { describe, expect, it } from "vitest";
import { chineseDemoContent } from "./chineseDemo";

describe("Chinese demo content", () => {
  it("translates fixture text and names without changing identifiers or source variants", () => {
    const source = {
      ticket: { subject: "Вопрос по продлению подписки", user_id: 42 },
      names: ["Антон 🚀", "Иван Кузнецов"],
      texts: { ru: "Технические работы", en: "Scheduled maintenance" },
      languages: [{ code: "ru", name: "Русский" }],
    };
    expect(chineseDemoContent(source)).toEqual({
      ticket: { subject: "关于订阅续费的问题", user_id: 42 },
      names: ["安东 🚀", "伊万 库兹涅佐夫"],
      texts: { ru: "Технические работы", en: "Scheduled maintenance", "zh-hans": "计划维护" },
      languages: [{ code: "ru", name: "Русский" }],
    });
    expect(source.ticket.subject).toBe("Вопрос по продлению подписки");
    expect(chineseDemoContent(null)).toBeNull();
  });
});
