import { afterEach, describe, expect, it, vi } from "vitest";

import { openInReusableTab, reusableTabTarget } from "./reusableTabTarget.ts";

const PR_URL = "https://github.com/imbue-ai/sculptor/pull/392";

describe("reusableTabTarget", () => {
  it("is stable: the same URL always maps to the same tab name", () => {
    expect(reusableTabTarget(PR_URL)).toBe(reusableTabTarget(PR_URL));
  });

  it("is distinct: different URLs map to different tab names", () => {
    expect(reusableTabTarget("https://github.com/o/r/pull/1")).not.toBe(
      reusableTabTarget("https://github.com/o/r/pull/2"),
    );
    // Same PR number in a different repo must not collapse into one tab.
    expect(reusableTabTarget("https://github.com/a/repo/pull/5")).not.toBe(
      reusableTabTarget("https://github.com/b/repo/pull/5"),
    );
  });

  it("never returns _blank, which forces a fresh tab on every click", () => {
    expect(reusableTabTarget(PR_URL)).not.toBe("_blank");
  });

  it("namespaces the name so it can't collide with a non-Sculptor window", () => {
    expect(reusableTabTarget(PR_URL)).toMatch(/^sculptor:/);
  });
});

describe("openInReusableTab", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("opens the URL in its stable, reusable named tab", () => {
    const open = vi.spyOn(window, "open").mockImplementation(() => null);
    openInReusableTab(PR_URL);
    expect(open).toHaveBeenCalledWith(PR_URL, reusableTabTarget(PR_URL));
  });

  it("does not pass noopener/noreferrer, which would defeat tab reuse", () => {
    const open = vi.spyOn(window, "open").mockImplementation(() => null);
    openInReusableTab(PR_URL);
    // Exactly (url, target): a third 'features' argument with noopener/noreferrer
    // would make the browser treat the named target as _blank and spawn a new tab.
    const call = open.mock.calls[0];
    expect(call).toHaveLength(2);
    expect(call[1]).not.toBe("_blank");
    expect(String(call[2] ?? "")).not.toContain("noopener");
  });
});
