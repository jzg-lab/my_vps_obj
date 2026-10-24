import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import {
  consoleAccessDenied,
  customerLabel,
  type ConsoleService,
  consoleSorts,
  consoleStatuses,
  readServicesRoute,
  servicesRouteUrl,
} from "./consoleServices";

describe("nullable customer identity", () => {
  const customer: ConsoleService["customer"] = {
    user_id: 42,
    minishop_id: "ms_42",
    first_name: null,
    last_name: null,
    email: null,
    username: null,
    is_banned: false,
  };
  it("keeps existing name, email, handle and account labels", () => {
    expect(customerLabel({ ...customer, first_name: "Ada", last_name: "Lovelace" })).toBe(
      "Ada Lovelace"
    );
    expect(customerLabel({ ...customer, email: "ada@example.test" })).toBe("ada@example.test");
    expect(customerLabel({ ...customer, username: "ada" })).toBe("@ada");
    expect(customerLabel(customer)).toBe("ms_42");
  });
  it("returns a string without manufacturing an archived identity", () => {
    expect(customerLabel({ ...customer, user_id: null, minishop_id: null, is_banned: null })).toBe(
      ""
    );
    expect(customerLabel({ ...customer, user_id: null })).toBe("");
    expect(customerLabel({ ...customer, minishop_id: null })).toBe("");
  });
});

describe("global services routes", () => {
  it("restores customer, filters, pagination and service detail", () => {
    const route = readServicesRoute(
      "?q=alice&status=sync_error&sort=expires_asc&page=3&service_id=service-a&user_id=42"
    );
    expect(route).toEqual({
      q: "alice",
      status: "sync_error",
      sort: "expires_asc",
      page: 3,
      serviceId: "service-a",
      userId: "42",
    });
    const url = servicesRouteUrl(
      "https://example.test/demo/runtime/admin/nodes?mock=services&nodes_q=Paris&nodes_page=2&node_id=node-a",
      route,
      "/demo/runtime"
    );
    expect(url.pathname).toBe("/demo/runtime/admin/services");
    expect(url.searchParams.get("nodes_q")).toBe("Paris");
    expect(url.searchParams.get("nodes_page")).toBe("2");
    expect(url.searchParams.get("mock")).toBe("services");
    expect(url.searchParams.has("node_id")).toBe(false);
    expect(readServicesRoute(url.search)).toEqual(route);
  });
  it.each(["-1", "1.5", "Infinity", "1000001", "bad"])("rejects invalid page %s", (page) => {
    expect(readServicesRoute(`?page=${page}`).page).toBe(0);
  });
  it("normalizes untrusted filters and clears a detail without losing list state", () => {
    expect(readServicesRoute("?status=not-a-status&sort=bad&user_id=anything")).toMatchObject({
      status: "all",
      sort: "created_desc",
      userId: "",
    });
    const route = readServicesRoute("?q=alice&page=2&service_id=service-a");
    const url = servicesRouteUrl("https://example.test/admin/services?service_id=service-a", {
      ...route,
      serviceId: "",
    });
    expect(url.searchParams.has("service_id")).toBe(false);
    expect(readServicesRoute(url.search)).toMatchObject({ q: "alice", page: 2 });
  });
});

describe("console cache permissions", () => {
  it("clears cached snapshots for auth denial, but permits stale source snapshots", () => {
    expect(consoleAccessDenied({ ok: false, error: "forbidden" })).toBe(true);
    expect(consoleAccessDenied({ ok: false, error: "unauthorized" })).toBe(true);
    expect(consoleAccessDenied(new Error("service_unavailable"))).toBe(false);
    expect(consoleAccessDenied(null)).toBe(false);
  });
});

describe("console filter translations", () => {
  it.each(["en", "ru", "zh-hans"])("provides every dynamic choice in %s", (lang) => {
    const locale: Record<string, string> = JSON.parse(
      readFileSync(new URL(`../../../../locales/${lang}.json`, import.meta.url), "utf8")
    );
    const keys = [
      "admin_console_all",
      ...consoleStatuses
        .filter((status) => status !== "all")
        .map((status) => `admin_console_filter_${status}`),
      ...consoleSorts.map((sort) => `admin_console_sort_${sort}`),
    ];
    for (const key of keys) expect(locale[key], key).toBeTruthy();
  });
});
