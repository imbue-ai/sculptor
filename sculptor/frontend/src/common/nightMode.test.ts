import { describe, expect, it } from "vitest";

import {
  formatNightModeExpiry,
  getDefaultNightModeExpiry,
  getNightModeExpiry,
  getNightModeKind,
  getNightModeSuppressionReason,
  isNightModeActive,
  NIGHT_MODE_OFF,
  NIGHT_MODE_ON,
  toDateTimeLocalValue,
} from "~/common/nightMode";

describe("getNightModeKind", () => {
  it("distinguishes the three stored states", () => {
    expect(getNightModeKind(NIGHT_MODE_OFF)).toBe("off");
    expect(getNightModeKind(NIGHT_MODE_ON)).toBe("on");
    expect(getNightModeKind("2026-09-10T08:00:00Z")).toBe("until");
  });
});

describe("isNightModeActive", () => {
  const now = new Date("2026-09-10T03:00:00Z");

  it("is never active when off", () => {
    expect(isNightModeActive(NIGHT_MODE_OFF, now)).toBe(false);
  });

  it("is always active when on", () => {
    expect(isNightModeActive(NIGHT_MODE_ON, now)).toBe(true);
  });

  it("stays active until the instant it names, then stops", () => {
    expect(isNightModeActive("2026-09-10T08:00:00Z", now)).toBe(true);
    expect(isNightModeActive("2026-09-10T08:00:00Z", new Date("2026-09-10T08:00:00Z"))).toBe(false);
    expect(isNightModeActive("2026-09-10T02:00:00Z", now)).toBe(false);
  });
});

describe("getNightModeExpiry", () => {
  it("returns the instant for a timestamp and null for the fixed states", () => {
    expect(getNightModeExpiry("2026-09-10T08:00:00Z")?.toISOString()).toBe("2026-09-10T08:00:00.000Z");
    expect(getNightModeExpiry(NIGHT_MODE_OFF)).toBeNull();
    expect(getNightModeExpiry(NIGHT_MODE_ON)).toBeNull();
  });
});

describe("getDefaultNightModeExpiry", () => {
  it("is the next 8am local, so the overnight case is one click", () => {
    // Late evening -> tomorrow morning.
    expect(getDefaultNightModeExpiry(new Date(2026, 8, 9, 23, 30))).toEqual(new Date(2026, 8, 10, 8, 0, 0, 0));
    // Small hours -> later the same morning.
    expect(getDefaultNightModeExpiry(new Date(2026, 8, 10, 3, 0))).toEqual(new Date(2026, 8, 10, 8, 0, 0, 0));
    // Exactly 8am -> the following day, never a moment already past.
    expect(getDefaultNightModeExpiry(new Date(2026, 8, 10, 8, 0))).toEqual(new Date(2026, 8, 11, 8, 0, 0, 0));
  });
});

describe("toDateTimeLocalValue", () => {
  it("renders local wall-clock time for the datetime-local input, not UTC", () => {
    expect(toDateTimeLocalValue(new Date(2026, 8, 10, 8, 5))).toBe("2026-09-10T08:05");
  });
});

describe("getNightModeSuppressionReason", () => {
  const now = new Date(2026, 8, 10, 3, 0);

  it("has nothing to explain while night mode is off or already expired", () => {
    expect(getNightModeSuppressionReason(NIGHT_MODE_OFF, now)).toBeNull();
    expect(getNightModeSuppressionReason(new Date(2026, 8, 10, 2, 0).toISOString(), now)).toBeNull();
  });

  it("explains an indefinite override without naming an end", () => {
    expect(getNightModeSuppressionReason(NIGHT_MODE_ON, now)).toBe("Night mode is on, so agents run without fast mode");
  });

  it("names when an expiring override ends", () => {
    const expiry = new Date(2026, 8, 10, 8, 0);
    const reason = getNightModeSuppressionReason(expiry.toISOString(), now);

    expect(reason).toBe(`Night mode is on until ${formatNightModeExpiry(expiry)}, so agents run without fast mode`);
    expect(reason).toContain("until");
  });
});
