import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { formatRelativeTime } from "./formatRelativeTime.ts";

const MINUTE_MS = 60000;
const HOUR_MS = 3600000;
const DAY_MS = 86400000;

describe("formatRelativeTime", () => {
  const NOW = new Date("2026-03-31T12:00:00.000Z");

  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(NOW);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  const ago = (ms: number): string => new Date(NOW.getTime() - ms).toISOString();

  it("returns 'just now' for timestamps less than 1 minute ago", () => {
    expect(formatRelativeTime(ago(30000))).toBe("just now");
  });

  it("returns minutes for timestamps less than 1 hour ago", () => {
    expect(formatRelativeTime(ago(1 * MINUTE_MS))).toBe("1m ago");
    expect(formatRelativeTime(ago(5 * MINUTE_MS))).toBe("5m ago");
    expect(formatRelativeTime(ago(45 * MINUTE_MS))).toBe("45m ago");
  });

  it("returns hours for timestamps less than 24 hours ago", () => {
    expect(formatRelativeTime(ago(1 * HOUR_MS))).toBe("1h ago");
    expect(formatRelativeTime(ago(5 * HOUR_MS))).toBe("5h ago");
    expect(formatRelativeTime(ago(23 * HOUR_MS))).toBe("23h ago");
  });

  it("returns '1d ago' for exactly 1 day ago", () => {
    expect(formatRelativeTime(ago(1 * DAY_MS))).toBe("1d ago");
  });

  it("returns days for 2-6 days ago", () => {
    expect(formatRelativeTime(ago(3 * DAY_MS))).toBe("3d ago");
    expect(formatRelativeTime(ago(6 * DAY_MS))).toBe("6d ago");
  });

  it("returns weeks for 7-29 days ago", () => {
    expect(formatRelativeTime(ago(7 * DAY_MS))).toBe("1w ago");
    expect(formatRelativeTime(ago(14 * DAY_MS))).toBe("2w ago");
    expect(formatRelativeTime(ago(21 * DAY_MS))).toBe("3w ago");
    expect(formatRelativeTime(ago(28 * DAY_MS))).toBe("4w ago");
    expect(formatRelativeTime(ago(29 * DAY_MS))).toBe("4w ago");
  });

  it("does NOT return '0mo ago' for 28-29 days", () => {
    const result28 = formatRelativeTime(ago(28 * DAY_MS));
    const result29 = formatRelativeTime(ago(29 * DAY_MS));
    expect(result28).not.toBe("0mo ago");
    expect(result29).not.toBe("0mo ago");
  });

  it("returns months for 30+ days ago", () => {
    expect(formatRelativeTime(ago(30 * DAY_MS))).toBe("1mo ago");
    expect(formatRelativeTime(ago(60 * DAY_MS))).toBe("2mo ago");
    expect(formatRelativeTime(ago(90 * DAY_MS))).toBe("3mo ago");
  });
});
