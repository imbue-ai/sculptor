import { useEffect, useRef, useState } from "react";

import { useInterval } from "../../../common/useInterval.ts";

type RelativeTimeResult = {
  relativeTime: string;
  absoluteTime: string;
};

const EMPTY_RESULT: RelativeTimeResult = { relativeTime: "", absoluteTime: "" };
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
  const [result, setResult] = useState<RelativeTimeResult>(() => {
    if (!isoTimestamp) {
      return EMPTY_RESULT;
    }
    return {
      relativeTime: computeRelativeTime(isoTimestamp),
      absoluteTime: computeAbsoluteTime(isoTimestamp),
    };
  });

  const previousRelativeTimeRef = useRef(result.relativeTime);

  useEffect(() => {
    if (!isoTimestamp) {
      setResult(EMPTY_RESULT);
      previousRelativeTimeRef.current = "";
      return;
    }

    const absoluteTime = computeAbsoluteTime(isoTimestamp);
    const relativeTime = computeRelativeTime(isoTimestamp);
    previousRelativeTimeRef.current = relativeTime;
    setResult({ relativeTime, absoluteTime });
  }, [isoTimestamp]);

  useInterval(() => {
    if (!isoTimestamp) return;

    const absoluteTime = computeAbsoluteTime(isoTimestamp);
    const newRelativeTime = computeRelativeTime(isoTimestamp);
    if (newRelativeTime !== previousRelativeTimeRef.current) {
      previousRelativeTimeRef.current = newRelativeTime;
      setResult({ relativeTime: newRelativeTime, absoluteTime });
    }
  }, UPDATE_INTERVAL_MS);

  return result;
}
