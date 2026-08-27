import { afterEach, describe, expect, it, vi } from "vitest";

import { syncStatusBarThemeColor } from "./statusBarThemeColor.ts";

const getMeta = (): HTMLMetaElement | null => {
  return document.head.querySelector<HTMLMetaElement>('meta[name="theme-color"]');
};

// jsdom does not resolve CSS custom properties, so the --gray-2 read is
// stubbed at the getComputedStyle boundary.
const stubComputedGray2 = (value: string): void => {
  vi.spyOn(window, "getComputedStyle").mockReturnValue({
    getPropertyValue: (property: string): string => (property === "--gray-2" ? value : ""),
  } as unknown as CSSStyleDeclaration);
};

describe("syncStatusBarThemeColor", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    getMeta()?.remove();
  });

  it("creates the meta tag with the computed --gray-2 color", () => {
    stubComputedGray2(" #212225 ");

    syncStatusBarThemeColor(document.createElement("div"), false);

    expect(getMeta()?.content).toBe("#212225");
  });

  it("updates an existing meta tag instead of adding another", () => {
    const existing = document.createElement("meta");
    existing.name = "theme-color";
    existing.content = "#f2f0e7";
    document.head.appendChild(existing);
    stubComputedGray2("#212225");

    syncStatusBarThemeColor(document.createElement("div"), false);

    expect(document.head.querySelectorAll('meta[name="theme-color"]')).toHaveLength(1);
    expect(existing.content).toBe("#212225");
  });

  it("leaves the document untouched when --gray-2 does not resolve", () => {
    stubComputedGray2("");

    syncStatusBarThemeColor(document.createElement("div"), false);

    expect(getMeta()).toBeNull();
  });

  it("pins the dev-preview color regardless of the theme", () => {
    stubComputedGray2("#212225");

    syncStatusBarThemeColor(document.createElement("div"), true);

    expect(getMeta()?.content).toBe("#f76b15");
  });
});
