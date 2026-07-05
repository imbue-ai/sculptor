import { describe, expect, it } from "vitest";

import type { AutoUpdateStatus } from "~/common/types/backend.ts";

import { getUpdateStatusText } from "./autoUpdate.ts";

const idleStatus = (latestChannelVersion: string): AutoUpdateStatus =>
  ({ type: "idle", latestChannelVersion }) as unknown as AutoUpdateStatus;

describe("getUpdateStatusText version comparison", () => {
  // Regression: version status used a lexicographic string compare which is
  // wrong for multi-digit minor/patch numbers; now it uses semver.lt. With a
  // lexicographic compare "0.10.0" < "0.9.0" is true, so the current version
  // would be incorrectly reported as "ahead of latest". semver knows 0.10.0
  // is newer than 0.9.0, so the correct text is "Up to date".
  it("does not call current 'ahead' when latest is a newer multi-digit minor", () => {
    const text = getUpdateStatusText(idleStatus("0.10.0"), "STABLE", "0.9.0");

    // Buggy (lexicographic) behavior would produce the "ahead of latest" string.
    expect(text).not.toContain("ahead");
    expect(text).toBe("Up to date — latest Stable release: v0.10.0.");
  });

  // Genuinely-ahead case still works: current newer than latest -> "ahead".
  it("reports 'ahead' when current is genuinely newer than latest", () => {
    const text = getUpdateStatusText(idleStatus("0.9.0"), "STABLE", "0.10.0");

    expect(text).toContain("ahead");
    expect(text).toBe("You're on v0.10.0, ahead of latest Stable release (v0.9.0).");
  });
});
