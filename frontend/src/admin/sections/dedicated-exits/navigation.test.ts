import { describe, expect, it } from "vitest";
import { dedicatedExitsUrl, readDedicatedExitsRoute } from "./navigation";

describe("dedicated exit ownership navigation", () => {
  it("restores inventory and audit pages after opening and closing a service", () => {
    const current =
      "https://console.test/app/admin/dedicated-exits?exits_page=2&exit_id=exit%2Fa%2Bb&exit_audit_page=3&nodes_q=HK%26EU&q=customer&page=7&lang=zh#content";
    const original = readDedicatedExitsRoute(new URL(current).search);
    const detail = dedicatedExitsUrl(current, { ...original, serviceId: "service/a+b" }, "/app");
    expect(detail.pathname).toBe("/app/admin/dedicated-exits");
    expect(detail.searchParams.get("section")).toBe("dedicated-exits");
    expect(readDedicatedExitsRoute(detail.search)).toEqual({
      page: 2,
      exitId: "exit/a+b",
      auditPage: 3,
      serviceId: "service/a+b",
    });
    const back = dedicatedExitsUrl(
      detail.href,
      { ...readDedicatedExitsRoute(detail.search), serviceId: "" },
      "/app"
    );
    expect(readDedicatedExitsRoute(back.search)).toEqual(original);
    expect(back.searchParams.has("exit_service_id")).toBe(false);
    for (const key of ["nodes_q", "q", "page", "lang"])
      expect(back.searchParams.get(key)).toBe(new URL(current).searchParams.get(key));
    expect(back.hash).toBe("#content");
  });

  it("keeps unrelated service, node and customer filters out of the exit selection", () => {
    expect(
      readDedicatedExitsRoute("?service_id=another-service&page=9&node_id=node&user_id=42")
    ).toEqual({ page: 0, exitId: "", auditPage: 0, serviceId: "" });
  });

  it.each(["-1", "NaN", "1.5", "Infinity", "1000001"])(
    "rejects an invalid inventory or audit page: %s",
    (page) => {
      expect(readDedicatedExitsRoute(`?exits_page=${page}&exit_audit_page=${page}`)).toMatchObject({
        page: 0,
        auditPage: 0,
      });
    }
  );

  it("removes closed evidence and default pages without removing unrelated context", () => {
    const url = dedicatedExitsUrl(
      "https://console.test/admin/dedicated-exits?exit_id=e1&exit_audit_page=4&exits_page=1&exit_service_id=s1&mock=services",
      readDedicatedExitsRoute("")
    );
    expect([...url.searchParams.entries()]).toEqual([
      ["mock", "services"],
      ["section", "dedicated-exits"],
    ]);
  });
});
