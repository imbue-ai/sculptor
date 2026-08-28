import { afterEach, describe, expect, it, vi } from "vitest";

import { isValidPageId, popPageStack, pushPageStack } from "../utils/pages.ts";

describe("page stack helpers", () => {
  it("pushes a new page on top", () => {
    expect(pushPageStack([], "theme.appearance")).toEqual(["theme.appearance"]);
    expect(pushPageStack(["theme.appearance"], "settings.section")).toEqual(["theme.appearance", "settings.section"]);
  });

  it("pops the top page", () => {
    expect(popPageStack(["theme.appearance", "settings.section"])).toEqual(["theme.appearance"]);
    expect(popPageStack(["agents.switch"])).toEqual([]);
  });

  it("popping an empty stack is a no-op", () => {
    expect(popPageStack([])).toEqual([]);
  });

  describe("invalid page id rejection", () => {
    afterEach(() => {
      vi.restoreAllMocks();
    });

    it("isValidPageId returns true for known ids and false for unknown", () => {
      expect(isValidPageId("settings.section")).toBe(true);
      expect(isValidPageId("theme.appearance")).toBe(true);
      expect(isValidPageId("not.a.real.page")).toBe(false);
    });

    it("pushPageStack ignores unknown page ids and logs an error", () => {
      const errSpy = vi.spyOn(console, "error").mockImplementation(() => {});
      const next = pushPageStack(["theme.appearance"], "bogus.page" as never);
      expect(next).toEqual(["theme.appearance"]);
      expect(errSpy).toHaveBeenCalledTimes(1);
      expect(errSpy.mock.calls[0]?.[0]).toContain("bogus.page");
    });
  });
});
