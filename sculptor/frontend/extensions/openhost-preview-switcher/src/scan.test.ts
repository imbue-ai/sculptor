import { describe, expect, it } from "vitest";

import { parsePreviewLabel, parsePreviewPort } from "./scan.ts";

describe("parsePreviewPort", () => {
  it("parses band ports at the boundaries and with trailing paths", () => {
    expect(parsePreviewPort("/proxy/51000/")).toBe(51000);
    expect(parsePreviewPort("/proxy/59999")).toBe(59999);
    expect(parsePreviewPort("/proxy/51042/some/asset.js")).toBe(51042);
  });

  it("rejects ports outside the 51000-59999 band", () => {
    expect(parsePreviewPort("/proxy/50999/")).toBeNull();
    expect(parsePreviewPort("/proxy/60000/")).toBeNull();
    expect(parsePreviewPort("/proxy/5100/")).toBeNull();
    expect(parsePreviewPort("/proxy/510000/")).toBeNull();
  });

  it("rejects non-preview paths", () => {
    expect(parsePreviewPort("/proxy/")).toBeNull();
    expect(parsePreviewPort("/")).toBeNull();
    expect(parsePreviewPort("/settings/proxy/51000/")).toBeNull();
  });
});

describe("parsePreviewLabel", () => {
  it("prefers the sculptor-preview meta over the title", () => {
    const html =
      '<head><meta name="sculptor-preview" content="my-branch@abc1234*" />' +
      "<title>Sculptor</title></head>";
    expect(parsePreviewLabel(html)).toBe("my-branch@abc1234*");
  });

  it("falls back to the document title", () => {
    expect(parsePreviewLabel("<head><title>Sculptor</title></head>")).toBe("Sculptor");
  });

  it("returns empty when neither is present", () => {
    expect(parsePreviewLabel("<html><body>502</body></html>")).toBe("");
  });
});
