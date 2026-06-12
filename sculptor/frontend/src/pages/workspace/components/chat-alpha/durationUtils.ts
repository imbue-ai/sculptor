/** Format a duration in seconds into a human-readable string (e.g. "3.2s" or "125.0s"). */
export const formatDuration = (seconds: number): string => {
  if (Number.isNaN(seconds)) return "0.0s";
  return `${seconds.toFixed(1)}s`;
};
