const MS_PER_MINUTE = 60_000;
const MINUTES_PER_HOUR = 60;
const HOURS_PER_DAY = 24;
const DAYS_PER_WEEK = 7;
const DAYS_PER_MONTH = 30;

/**
 * Formats an ISO date string as a relative time label (e.g. "3m ago", "2h ago", "3d ago", "2w ago", "1mo ago").
 */
export const formatRelativeTime = (isoDate: string): string => {
  const date = new Date(isoDate);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMinutes = Math.floor(diffMs / MS_PER_MINUTE);
  const diffHours = Math.floor(diffMinutes / MINUTES_PER_HOUR);
  const diffDays = Math.floor(diffHours / HOURS_PER_DAY);
  const diffWeeks = Math.floor(diffDays / DAYS_PER_WEEK);
  const diffMonths = Math.floor(diffDays / DAYS_PER_MONTH);

  if (diffMinutes < 1) return "just now";
  if (diffMinutes < MINUTES_PER_HOUR) return `${diffMinutes}m ago`;
  if (diffHours < HOURS_PER_DAY) return `${diffHours}h ago`;
  if (diffDays === 1) return "1d ago";
  if (diffDays < DAYS_PER_WEEK) return `${diffDays}d ago`;
  if (diffMonths < 1) return `${diffWeeks}w ago`;
  return `${diffMonths}mo ago`;
};
