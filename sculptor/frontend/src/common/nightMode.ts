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

export type NightModeState =
  | { readonly kind: "off" }
  | { readonly kind: "on" }
  | { readonly kind: "until"; readonly expiry: Date };

export type NightModeKind = NightModeState["kind"];

/**
 * Resolve the stored string into its case.
 *
 * The generated API type widens the backend's three-case union to `string`, so
 * this is where the frontend pins the value down. An instant it cannot parse
 * resolves to "off", leaving agents on the user's own fast-mode choice rather
 * than suppressing it on the strength of a value nobody can read.
 */
export const parseNightMode = (nightMode: string): NightModeState => {
  if (nightMode === NIGHT_MODE_OFF) {
    return { kind: "off" };
  }

  if (nightMode === NIGHT_MODE_ON) {
    return { kind: "on" };
  }
  const expiry = new Date(nightMode);
  return Number.isNaN(expiry.getTime()) ? { kind: "off" } : { kind: "until", expiry };
};

export const isNightModeActive = (nightMode: string, now: Date): boolean => {
  const state = parseNightMode(nightMode);
  switch (state.kind) {
    case "off":
      return false;
    case "on":
      return true;
    case "until":
      return now < state.expiry;
  }
};

const NIGHT_MODE_DEFAULT_WAKE_HOUR = 8;

/**
 * The next 8am local time — when a night's work is expected to be picked back up.
 *
 * Prefilling this makes the overnight case a single choice rather than a date
 * and a time. Only an 8am still ahead is offered; a past instant would leave
 * night mode inert.
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
 * it returns on its own once night mode lapses.
 */
export const getNightModeSuppressionReason = (nightMode: string, now: Date): string | null => {
  const state = parseNightMode(nightMode);
  switch (state.kind) {
    case "off":
      return null;
    case "on":
      return "Night mode is on, so agents run without fast mode";
    case "until":
      return now < state.expiry
        ? `Night mode is on until ${formatNightModeExpiry(state.expiry)}, so agents run without fast mode`
        : null;
  }
};
