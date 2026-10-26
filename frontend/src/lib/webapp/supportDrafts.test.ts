import { afterEach, describe, expect, it, vi } from "vitest";
import { prepareServiceSupportDraft, readSupportDraft, writeSupportDraft } from "./supportDrafts";
import { parseTelegramHtml } from "../richtext/telegramHtml";

afterEach(() => vi.unstubAllGlobals());
describe("service support drafts", () => {
  it("preserves the current account draft and adds a safe service reference only once", () => {
    const values = new Map<string, string>();
    vi.stubGlobal("window", {
      localStorage: {
        getItem: (key: string) => values.get(key) ?? null,
        setItem: (key: string, value: string) => values.set(key, value),
        removeItem: (key: string) => values.delete(key),
      },
    });
    writeSupportDraft("new", "account-a", "new", {
      subject: "My issue",
      body: "<b>Keep my text</b>",
      priority: "high",
      category: "technical",
    });
    const id = "a".repeat(32);
    prepareServiceSupportDraft("account-a", id, "<Service>");
    prepareServiceSupportDraft("account-a", id, "<Service>");
    const draft = readSupportDraft("new", "account-a");
    expect(draft).toMatchObject({
      subject: "My issue",
      priority: "high",
      category: "technical",
      open: true,
    });
    expect(draft?.body).toBe("<b>Keep my text</b>\n\n&lt;Service&gt;: " + id);
    expect(parseTelegramHtml(String(draft?.body)).unknownTags).toEqual([]);
    expect(readSupportDraft("new", "account-b")).toBeNull();
    prepareServiceSupportDraft("account-b", "invalid/subscription-token", "Service");
    expect(readSupportDraft("new", "account-b")).toBeNull();
  });
  it("does not block navigation when storage is unavailable", () => {
    vi.stubGlobal("window", {});
    expect(() => prepareServiceSupportDraft("account", "a".repeat(32), "Service")).not.toThrow();
  });
});
