import { describe, expect, it, vi } from "vitest";
import {
  clearConsoleNodeMetadata,
  consoleNodeCountryLabel,
  consoleNodeMetadataDraftReady,
  consoleNodeMetadataErrorKey,
  saveConsoleNodeMetadata,
} from "./consoleNodeMetadata";

describe("console node metadata", () => {
  it("normalizes and saves only local display fields against the remote UUID", async () => {
    const api = vi.fn().mockResolvedValue({
      ok: true,
      node_id: "node-uuid",
      display_name: "Tokyo relay",
      region: "Tokyo",
      provider: "Example Networks",
      updated_at: "2026-10-27T00:00:00Z",
    });
    const saved = await saveConsoleNodeMetadata(api as never, "node-uuid", {
      display_name: " Tokyo relay ",
      region: " Tokyo ",
      provider: " Example Networks ",
    });
    expect(api).toHaveBeenCalledWith(
      "/admin/console/nodes/node-uuid/metadata",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({
          display_name: "Tokyo relay",
          region: "Tokyo",
          provider: "Example Networks",
        }),
      })
    );
    expect(saved.node_id).toBe("node-uuid");
  });

  it("clears local labels and handles field length and API errors", async () => {
    const api = vi.fn().mockResolvedValue({ ok: true, node_id: "node-uuid", deleted: true });
    await clearConsoleNodeMetadata(api as never, "node-uuid");
    expect(api).toHaveBeenCalledWith("/admin/console/nodes/node-uuid/metadata", {
      method: "DELETE",
    });
    expect(
      consoleNodeMetadataDraftReady({ display_name: "x".repeat(120), region: "", provider: "" })
    ).toBe(true);
    expect(
      consoleNodeMetadataDraftReady({ display_name: "x".repeat(121), region: "", provider: "" })
    ).toBe(false);
    expect(consoleNodeMetadataErrorKey({ error: "node_not_found" })).toBe(
      "console_node_metadata_not_found"
    );
  });

  it("renders country codes in the selected language and preserves unknown values", () => {
    expect(consoleNodeCountryLabel("US", "en")).toBe("United States (US)");
    expect(consoleNodeCountryLabel("US", "zh-Hans")).toContain("美国");
    expect(consoleNodeCountryLabel(null, "en")).toBeNull();
    expect(consoleNodeCountryLabel("unknown", "en")).toBe("unknown");
  });
});
