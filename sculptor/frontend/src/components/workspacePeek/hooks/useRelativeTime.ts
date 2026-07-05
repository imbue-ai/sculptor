import { useState } from "react";

import { useInterval } from "../../../common/hooks/useInterval.ts";

type RelativeTimeResult = {
  relativeTime: string;
  absoluteTime: string;
};

const EMPTY_RESULT: RelativeTimeResult = { relativeTime: "", absoluteTime: "" };
const UPDATE_INTERVAL_MS = 60_000;

const computeRelativeTime = (isoTimestamp: string): string => {
  const now = Date.now();
  const then = new Date(isoTimestamp).getTime();
  const diffSeconds = Math.floor((now - then) / 1000);

  if (diffSeconds < 60) {
    return "just now";
  }

  const diffMinutes = Math.floor(diffSeconds / 60);
  if (diffMinutes < 60) {
    return `${diffMinutes}m ago`;
  }

  const diffHours = Math.floor(diffMinutes / 60);
  if (diffHours < 24) {
    return `${diffHours}h ago`;
  }

  const diffDays = Math.floor(diffHours / 24);
  if (diffDays < 7) {
    return `${diffDays}d ago`;
  }

  const diffWeeks = Math.floor(diffDays / 7);
  return `${diffWeeks}w ago`;
};

const computeAbsoluteTime = (isoTimestamp: string): string => {
  const date = new Date(isoTimestamp);
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
};

const computeResult = (isoTimestamp: string | null | undefined): RelativeTimeResult => {
  if (!isoTimestamp) {
    return EMPTY_RESULT;
  }
  return {
    relativeTime: computeRelativeTime(isoTimestamp),
    absoluteTime: computeAbsoluteTime(isoTimestamp),
  };
};

export const useRelativeTime = (isoTimestamp: string | null | undefined): RelativeTimeResult => {
  // Derive the displayed value during render from the timestamp, so it always
  // reflects the latest `isoTimestamp` without an effect. The interval below
  // forces a re-render on a schedule so the relative time recomputes as
  // wall-clock time advances.
  const result = computeResult(isoTimestamp);

  // `tick` is never read; bumping it from the interval simply forces a
  // re-render so the derived `result` above recomputes against the new time.
  const [tick, setTick] = useState(0);
  void tick;

  useInterval(() => {
    if (!isoTimestamp) return;

    // Re-render only when the displayed relative time would actually change,
    // preserving the original update cadence. `result.relativeTime` is captured
    // from the latest render, since useInterval always calls the latest callback.
    const newRelativeTime = computeRelativeTime(isoTimestamp);
    if (newRelativeTime !== result.relativeTime) {
      setTick((current) => current + 1);
    }
  }, UPDATE_INTERVAL_MS);

  return result;
};
