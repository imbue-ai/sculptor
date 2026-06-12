import { describe, expect, it } from "vitest";

import type { ChatMessage } from "~/api";

import {
  formatAbsoluteTimestamp,
  formatHumanTimestamp,
  formatRelativeTimestamp,
  formatTimestamp,
  getPromptCycleBaselines,
} from "./timestampUtils.ts";

const BASE_TIME = "2026-03-09T14:30:00.000Z";
const offsetMs = (ms: number): string => new Date(new Date(BASE_TIME).getTime() + ms).toISOString();

const makeMessage = (role: "USER" | "ASSISTANT", time: string): ChatMessage =>
  ({
    id: `msg-${role}-${time}`,
    role,
    content: [{ type: "text", text: "test" }],
    approximateCreationTime: time,
  }) as unknown as ChatMessage;

describe("formatRelativeTimestamp", () => {
  it("returns T+0.0s when timestamp equals baseline", () => {
    expect(formatRelativeTimestamp(BASE_TIME, BASE_TIME)).toBe("T+0.0s");
  });

  it("formats positive offset in seconds with one decimal", () => {
    expect(formatRelativeTimestamp(offsetMs(1200), BASE_TIME)).toBe("T+1.2s");
  });

  it("formats larger offsets correctly", () => {
    expect(formatRelativeTimestamp(offsetMs(15000), BASE_TIME)).toBe("T+15.0s");
  });

  it("formats sub-second offsets", () => {
    expect(formatRelativeTimestamp(offsetMs(500), BASE_TIME)).toBe("T+0.5s");
  });
});

describe("formatAbsoluteTimestamp", () => {
  it("formats a UTC timestamp as local HH:MM:SS.mmm", () => {
    const result = formatAbsoluteTimestamp(BASE_TIME);
    // The exact output depends on the local timezone, but the format must be HH:MM:SS.mmm
    expect(result).toMatch(/^\d{2}:\d{2}:\d{2}\.\d{3}$/);
  });

  it("pads single-digit values", () => {
    // 2026-01-01T01:02:03.004Z — in UTC this is 01:02:03.004
    const result = formatAbsoluteTimestamp("2026-01-01T01:02:03.004Z");
    expect(result).toMatch(/^\d{2}:\d{2}:\d{2}\.\d{3}$/);
  });
});

describe("getPromptCycleBaselines", () => {
  it("returns empty array for empty messages", () => {
    expect(getPromptCycleBaselines([])).toEqual([]);
  });

  it("uses first message timestamp as initial baseline", () => {
    const messages = [makeMessage("ASSISTANT", offsetMs(0)), makeMessage("ASSISTANT", offsetMs(1000))];
    const baselines = getPromptCycleBaselines(messages);
    expect(baselines).toEqual([offsetMs(0), offsetMs(0)]);
  });

  it("resets baseline on each USER message", () => {
    const messages = [
      makeMessage("USER", offsetMs(0)),
      makeMessage("ASSISTANT", offsetMs(1000)),
      makeMessage("ASSISTANT", offsetMs(2000)),
      makeMessage("USER", offsetMs(10000)),
      makeMessage("ASSISTANT", offsetMs(11000)),
    ];
    const baselines = getPromptCycleBaselines(messages);
    expect(baselines).toEqual([offsetMs(0), offsetMs(0), offsetMs(0), offsetMs(10000), offsetMs(10000)]);
  });

  it("handles consecutive USER messages", () => {
    const messages = [
      makeMessage("USER", offsetMs(0)),
      makeMessage("USER", offsetMs(5000)),
      makeMessage("ASSISTANT", offsetMs(6000)),
    ];
    const baselines = getPromptCycleBaselines(messages);
    expect(baselines).toEqual([offsetMs(0), offsetMs(5000), offsetMs(5000)]);
  });
});

describe("formatTimestamp", () => {
  it("delegates to formatRelativeTimestamp when format is 'relative'", () => {
    const result = formatTimestamp(offsetMs(2500), BASE_TIME, "relative");
    expect(result).toBe("T+2.5s");
  });

  it("delegates to formatAbsoluteTimestamp when format is 'absolute'", () => {
    const result = formatTimestamp(BASE_TIME, BASE_TIME, "absolute");
    expect(result).toMatch(/^\d{2}:\d{2}:\d{2}\.\d{3}$/);
  });
});

describe("formatHumanTimestamp", () => {
  // Use a fixed "now" so tests don't depend on the real clock.
  // BASE_TIME is 2026-03-09T14:30:00.000Z
  const now = new Date("2026-03-09T18:00:00.000Z");

  it("shows time only for today", () => {
    const result = formatHumanTimestamp(BASE_TIME, now);
    // Should match a pattern like "2:30 PM" or "7:30 AM" (depends on local TZ)
    expect(result).toMatch(/^\d{1,2}:\d{2}\s[AP]M$/);
  });

  it("shows 'Yesterday' prefix for yesterday", () => {
    const yesterday = "2026-03-08T14:30:00.000Z";
    const result = formatHumanTimestamp(yesterday, now);
    expect(result).toMatch(/^Yesterday \d{1,2}:\d{2}\s[AP]M$/);
  });

  it("shows month and day for older dates in the same year", () => {
    const olderSameYear = "2026-01-15T10:00:00.000Z";
    const result = formatHumanTimestamp(olderSameYear, now);
    expect(result).toMatch(/^Jan 15, \d{1,2}:\d{2}\s[AP]M$/);
  });

  it("shows month, day, and year for dates in a different year", () => {
    const differentYear = "2025-06-20T08:00:00.000Z";
    const result = formatHumanTimestamp(differentYear, now);
    expect(result).toMatch(/^Jun 20, 2025, \d{1,2}:\d{2}\s[AP]M$/);
  });

  it("defaults to current time when now is not provided", () => {
    // Just verify it returns a string without throwing
    const result = formatHumanTimestamp(BASE_TIME);
    expect(typeof result).toBe("string");
    expect(result.length).toBeGreaterThan(0);
  });
});
