import { render } from "svelte/server";
import { describe, expect, it } from "vitest";
import AdminSelect from "./AdminSelect.svelte";

describe("AdminSelect label wrapping", () => {
  it.each([false, true])("keeps wrapping opt-in: %s", (wrapLabels) => {
    const label = "Profile · 20000000-0000-0000-0000-000000000002";
    const result = render(AdminSelect, {
      props: {
        value: "profile",
        items: [{ value: "profile", label }],
        ...(wrapLabels ? { wrapLabels } : {}),
      },
    }).body;
    expect(result).toContain(label);
    expect(result.includes("admin-select-wrap")).toBe(wrapLabels);
  });
});
