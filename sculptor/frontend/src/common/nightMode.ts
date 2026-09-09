/**
 * The global night-mode override, which forces every Claude agent off fast mode.
 *
 * The setting is stored as a single value with three cases — `"off"`, `"on"`, or
 * the ISO instant the override expires — so no combination of fields can express
 * a contradictory state. The expiry is an absolute instant rather than a
 * wall-clock time, so it survives a restart, a timezone change, and a machine
 * that was asleep when it passed.
 *
 * The backend re-resolves this at every turn launch and is authoritative. The
 * helpers here drive the settings UI and the chat toggle's disabled state, so
 * the UI never claims a turn will run fast when it will not.
 */

export const NIGHT_MODE_OFF = "off";
export const NIGHT_MODE_ON = "on";

export type NightModeKind = "off" | "on" | "until";

export const getNightModeKind = (nightMode: string): NightModeKind => {
  if (nightMode === NIGHT_MODE_OFF) {
    return "off";
  }

  if (nightMode === NIGHT_MODE_ON) {
    return "on";
  }
  return "until";
};

export const getNightModeExpiry = (nightMode: string): Date | null => {
  if (getNightModeKind(nightMode) !== "until") {
    return null;
  }
  const expiry = new Date(nightMode);
  return Number.isNaN(expiry.getTime()) ? null : expiry;
};

export const isNightModeActive = (nightMode: string, now: Date): boolean => {
  const kind = getNightModeKind(nightMode);
  if (kind === "off") {
    return false;
  }

  if (kind === "on") {
    return true;
  }
  const expiry = getNightModeExpiry(nightMode);
  return expiry !== null && now < expiry;
};

const NIGHT_MODE_DEFAULT_WAKE_HOUR = 8;

/**
 * The next 8am local time — when a night's work is expected to be picked back up.
 *
 * Prefilling this makes the overnight case a single choice rather than a date
 * and a time. An expiry that has already passed would leave night mode inert,
 * so 8am today is only offered while it is still ahead.
 */
export const getDefaultNightModeExpiry = (now: Date): Date => {
  const expiry = new Date(now);
  expiry.setHours(NIGHT_MODE_DEFAULT_WAKE_HOUR, 0, 0, 0);
  if (expiry <= now) {
    expiry.setDate(expiry.getDate() + 1);
  }
  return expiry;
};

const padToTwoDigits = (value: number): string => String(value).padStart(2, "0");

/** `<input type="datetime-local">` reads and writes local wall-clock time, never UTC. */
export const toDateTimeLocalValue = (date: Date): string =>
  `${date.getFullYear()}-${padToTwoDigits(date.getMonth() + 1)}-${padToTwoDigits(date.getDate())}` +
  `T${padToTwoDigits(date.getHours())}:${padToTwoDigits(date.getMinutes())}`;

/** A short, unambiguous rendering of when an override lapses, e.g. "Thu, 8:00 AM". */
export const formatNightModeExpiry = (expiry: Date): string =>
  expiry.toLocaleString(undefined, { weekday: "short", hour: "numeric", minute: "2-digit" });

/**
 * Why fast mode is unavailable right now, or null when it is available.
 *
 * The fast-mode preference is overridden for display rather than overwritten, so
 * it returns on its own once night mode lapses; this is the text that keeps the
 * toggle from silently disagreeing with what the agent will actually do.
 */
export const getNightModeSuppressionReason = (nightMode: string, now: Date): string | null => {
  if (!isNightModeActive(nightMode, now)) {
    return null;
  }
  const expiry = getNightModeExpiry(nightMode);
  if (expiry === null) {
    return "Night mode is on, so agents run without fast mode";
  }
  return `Night mode is on until ${formatNightModeExpiry(expiry)}, so agents run without fast mode`;
};
