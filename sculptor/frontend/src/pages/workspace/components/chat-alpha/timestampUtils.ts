import type { ChatMessage } from "~/api";

export type TimestampFormat = "relative" | "absolute";

/**
 * Format a timestamp relative to a baseline (e.g., "T+2.3s").
 * The baseline is typically the timestamp of the most recent USER message.
 */
export const formatRelativeTimestamp = (timestamp: string, baseTimestamp: string): string => {
  const messageTime = new Date(timestamp).getTime();
  const baseTime = new Date(baseTimestamp).getTime();
  const relativeMs = messageTime - baseTime;
  const relativeSeconds = (relativeMs / 1000).toFixed(1);
  return `T+${relativeSeconds}s`;
};

/**
 * Format a timestamp as absolute local time (e.g., "14:32:05.123").
 */
export const formatAbsoluteTimestamp = (timestamp: string): string => {
  const date = new Date(timestamp);
  const hours = date.getHours().toString().padStart(2, "0");
  const minutes = date.getMinutes().toString().padStart(2, "0");
  const seconds = date.getSeconds().toString().padStart(2, "0");
  const ms = date.getMilliseconds().toString().padStart(3, "0");
  return `${hours}:${minutes}:${seconds}.${ms}`;
};

/**
 * Build an array of baseline timestamps — one per message — where each
 * baseline is the `approximateCreationTime` of the most recent USER message
 * at or before that index. T+0 resets with each user prompt so relative
 * timestamps show how long the assistant took within the current turn.
 */
export const getPromptCycleBaselines = (messages: ReadonlyArray<ChatMessage>): ReadonlyArray<string> => {
  const baselines: Array<string> = [];
  let currentBaseline = messages[0]?.approximateCreationTime ?? "";
  for (const message of messages) {
    if (message.role === "USER") {
      currentBaseline = message.approximateCreationTime;
    }
    baselines.push(currentBaseline);
  }
  return baselines;
};

/**
 * Format a timestamp based on the selected format.
 */
export const formatTimestamp = (timestamp: string, baseTimestamp: string, format: TimestampFormat): string =>
  format === "relative" ? formatRelativeTimestamp(timestamp, baseTimestamp) : formatAbsoluteTimestamp(timestamp);

/**
 * Format a timestamp as human-readable text for the alpha view.
 *
 * Adapts to recency:
 * - Today:      "2:30 PM"
 * - Yesterday:  "Yesterday 2:30 PM"
 * - This year:  "Mar 7, 2:30 PM"
 * - Older:      "Mar 7, 2025, 2:30 PM"
 *
 * Accepts an optional `now` parameter for testability (defaults to current time).
 */
export const formatHumanTimestamp = (timestamp: string, now?: Date): string => {
  const date = new Date(timestamp);
  const reference = now ?? new Date();

  const timeStr = date.toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  });

  // Compare calendar dates in local time
  const dateDay = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  const refDay = new Date(reference.getFullYear(), reference.getMonth(), reference.getDate());
  const dayDiff = Math.round((refDay.getTime() - dateDay.getTime()) / (1000 * 60 * 60 * 24));

  if (dayDiff === 0) {
    return timeStr;
  }

  if (dayDiff === 1) {
    return `Yesterday ${timeStr}`;
  }

  const month = date.toLocaleString("en-US", { month: "short" });
  const day = date.getDate();

  if (date.getFullYear() === reference.getFullYear()) {
    return `${month} ${day}, ${timeStr}`;
  }

  return `${month} ${day}, ${date.getFullYear()}, ${timeStr}`;
};
