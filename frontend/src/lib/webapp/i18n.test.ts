import { describe, expect, it } from "vitest";

import { createI18n } from "./i18n.js";

describe("i18n language loading", () => {
  it("accepts a configured language before its dictionary has loaded", () => {
    let selectedLanguage = "ru";
    const i18n = createI18n({
      messages: { ru: { wa_title: "Название" } },
      supportedLanguages: ["ru", "it"],
      getLang: () => selectedLanguage,
    });

    expect(i18n.normalizeLangCode("it")).toBe("it");
    selectedLanguage = "it";
    i18n.mergeMessages({ it: { wa_title: "Titolo" } });
    expect(i18n.t("wa_title")).toBe("Titolo");
  });
});

describe("Simplified Chinese", () => {
  it("loads the same catalog for Simplified Chinese browser and account tags", () => {
    const i18n = createI18n({
      messages: { "zh-hans": { wa_services_title: "我的服务" } },
      defaultLang: "en",
      getLang: () => "zh-CN",
    });
    for (const language of ["zh", "zh-CN", "zh_SG", "zh-Hans", "zh-Hans-CN"]) {
      expect(i18n.normalizeLangCode(language)).toBe("zh-hans");
    }
    expect(i18n.t("wa_services_title")).toBe("我的服务");
    expect(i18n.languageName("zh-CN")).toBe("简体中文");
    expect(i18n.normalizeLangCode("zh-TW")).toBe("en");
    expect(i18n.normalizeLangCode("zh-Hant")).toBe("en");
  });
});
