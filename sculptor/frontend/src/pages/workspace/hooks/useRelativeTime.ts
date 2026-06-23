import { useRef, useState } from "react";

import { useInterval } from "../../../common/useInterval.ts";

type RelativeTimeResult = {
  relativeTime: string;
  absoluteTime: string;
};

const UPDATE_INTERVAL_MS = 60_000;

function computeRelativeTime(isoTimestamp: string): string {
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
}

function computeAbsoluteTime(isoTimestamp: string): string {
  const date = new Date(isoTimestamp);
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export function useRelativeTime(isoTimestamp: string | null | undefined): RelativeTimeResult {
  // `relativeTime` depends on the current wall-clock time, so it is held in
  // state and refreshed by the interval below. `absoluteTime` depends only on
  // the timestamp, so it is derived during render rather than stored.
  const [relativeTime, setRelativeTime] = useState<string>(() =>
    isoTimestamp ? computeRelativeTime(isoTimestamp) : "",
  );

  // Recompute immediately when the timestamp changes instead of waiting for the
  // next interval tick. Adjusting state during render avoids the stale
  // intermediate render a prop-syncing useEffect would produce.
  const previousTimestampRef = useRef(isoTimestamp);
  if (previousTimestampRef.current !== isoTimestamp) {
    previousTimestampRef.current = isoTimestamp;
    setRelativeTime(isoTimestamp ? computeRelativeTime(isoTimestamp) : "");
  }

  useInterval(() => {
    if (!isoTimestamp) {
      return;
    }
    // Setting an unchanged string is a no-op render thanks to React's bail-out,
    // so this only re-renders when the displayed value actually advances.
    setRelativeTime(computeRelativeTime(isoTimestamp));
  }, UPDATE_INTERVAL_MS);

  const absoluteTime = isoTimestamp ? computeAbsoluteTime(isoTimestamp) : "";
  return { relativeTime, absoluteTime };
}
