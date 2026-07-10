/** Workspace-switch profiler.
 *
 * Records how long a workspace switch takes to reach each rendering
 * milestone, so "tab switching feels slow" can be measured instead of
 * eyeballed. A switch starts in `useImbueNavigate` (markSwitchStart) and
 * milestones are reported from the layout code paths as they complete.
 *
 * Every milestone is a real `performance.mark()` with a `ws-switch.` prefix,
 * so when tracing is enabled (see common/tracing.ts) the marks flow into the
 * Perfetto trace with no extra wiring. Because mark timestamps are relative to
 * `performance.timeOrigin`, external frame-capture tooling can add that origin
 * to line the marks up with compositor frames on a shared wall clock.
 *
 * Enabled when any of:
 *   - `window.__WS_SWITCH_PROFILER__ === true` (set by test/capture harnesses
 *     via an init script, before app code runs)
 *   - backend tracing is on (`window.__SCULPTOR_TRACING__.enabled`)
 *   - dev builds, unless opted out via localStorage
 *     `sculptor-ws-switch-profiler` = "0"
 *
 * When disabled every export is inert — the production cost is one boolean
 * check per call, matching the bar set by `traceMark`.
 */

export const WS_SWITCH_MILESTONES = [
  // WorkspacePageContent rendered with the new workspace id.
  "page-content-render",
  // The new workspace's panel layout was loaded into the layout atoms.
  "layout-restored",
  // First frame painted after the layout restore (double-rAF approximation).
  // Frames between `start` and this mark are the stale-content window.
  "first-paint-after-restore",
] as const;

export type WsSwitchMilestone = (typeof WS_SWITCH_MILESTONES)[number];

export type WsSwitchTimingRecord = {
  fromWorkspaceId: string | null;
  toWorkspaceId: string;
  /** Epoch milliseconds of the switch start, for correlation with external clocks. */
  startedAtEpochMs: number;
  /** `performance.now()` at the switch start. */
  startedAtMs: number;
  /** Milliseconds from start to each milestone. Missing = never reached. */
  milestoneDeltasMs: Partial<Record<WsSwitchMilestone, number>>;
  /** True when the record was closed by the timeout rather than completion. */
  isTimedOut: boolean;
};

// The Window augmentation lives in this module rather than globals.d.ts so any
// program that pulls the profiler in can compile it — the extension-SDK .d.ts
// rollup builds from the SDK entry alone and never sees ambient declaration files.
declare global {
  // eslint-disable-next-line @typescript-eslint/consistent-type-definitions
  interface Window {
    /** Inlined by the backend's static-HTML serve path when --trace-to is set.
     * The renderer reads this synchronously at boot in common/tracing.ts. */
    __SCULPTOR_TRACING__?: { enabled: boolean };
    /** Opts the workspace-switch profiler in (set by perf/capture harnesses). */
    __WS_SWITCH_PROFILER__?: boolean;
    /** Finalized workspace-switch timing records, appended by the profiler. */
    __WS_SWITCH_TIMINGS__?: Array<WsSwitchTimingRecord>;
  }
}

// A switch that hasn't produced all milestones after this long is finalized
// as-is, in case a render milestone legitimately never fires.
const FINALIZE_TIMEOUT_MS = 5000;

// Cap on window.__WS_SWITCH_TIMINGS__ so a long session can't grow it unboundedly.
const MAX_RETAINED_RECORDS = 50;

let isEnabledCache: boolean | null = null;

const isProfilerEnabled = (): boolean => {
  if (isEnabledCache === null) {
    let isDevOptedIn = false;
    try {
      isDevOptedIn = import.meta.env.DEV && localStorage.getItem("sculptor-ws-switch-profiler") !== "0";
    } catch {
      // localStorage unavailable — treat as opted out
    }
    isEnabledCache =
      window.__WS_SWITCH_PROFILER__ === true || window.__SCULPTOR_TRACING__?.enabled === true || isDevOptedIn;
  }
  return isEnabledCache;
};

type PendingSwitch = {
  record: WsSwitchTimingRecord;
  timeoutId: ReturnType<typeof setTimeout>;
};

let pendingSwitch: PendingSwitch | null = null;

const safeMark = (name: string): void => {
  try {
    performance.mark(name);
  } catch (e) {
    // `performance.mark` only throws DOMException in supported browsers;
    // anything else is a programming bug and should surface.
    if (!(e instanceof DOMException)) throw e;
  }
};

const finalizePendingSwitch = (isTimedOut: boolean): void => {
  if (pendingSwitch === null) return;
  const { record, timeoutId } = pendingSwitch;
  pendingSwitch = null;
  clearTimeout(timeoutId);
  record.isTimedOut = isTimedOut;

  const timings = (window.__WS_SWITCH_TIMINGS__ ??= []);
  timings.push(record);
  if (timings.length > MAX_RETAINED_RECORDS) {
    timings.splice(0, timings.length - MAX_RETAINED_RECORDS);
  }

  const deltas = record.milestoneDeltasMs;
  const totalMs = Math.max(0, ...Object.values(deltas));
  const summary = WS_SWITCH_MILESTONES.map(
    (m) => `${m} ${deltas[m] !== undefined ? `${Math.round(deltas[m])}ms` : "—"}`,
  ).join(", ");
  console.log(
    `[ws-switch] ${record.fromWorkspaceId ?? "(none)"} → ${record.toWorkspaceId}: ` +
      `total ${Math.round(totalMs)}ms${isTimedOut ? " (timed out)" : ""} — ${summary}`,
  );
};

const hasAllMilestones = (record: WsSwitchTimingRecord): boolean =>
  WS_SWITCH_MILESTONES.every((m) => record.milestoneDeltasMs[m] !== undefined);

/** Parse the active workspace id out of the hash-router URL, e.g.
 * `#/ws/<id>/agent/<agentId>` → `<id>`. Null on non-workspace routes. */
const workspaceIdFromLocation = (): string | null => {
  const match = window.location.hash.match(/^#\/ws\/(?!new\b)([^/?]+)/);
  return match ? match[1] : null;
};

/**
 * Begin recording a workspace switch. Called from the navigation primitives
 * (`useImbueNavigate`) right before the URL changes. No-ops when the target
 * workspace is already active (e.g. switching agents within a workspace).
 */
export const markSwitchStart = (toWorkspaceId: string): void => {
  if (!isProfilerEnabled()) return;
  const fromWorkspaceId = workspaceIdFromLocation();
  if (fromWorkspaceId === toWorkspaceId) return;

  // A new switch starting before the previous one completed closes it as-is.
  finalizePendingSwitch(true);
  safeMark("ws-switch.start");
  pendingSwitch = {
    record: {
      fromWorkspaceId,
      toWorkspaceId,
      startedAtEpochMs: Date.now(),
      startedAtMs: performance.now(),
      milestoneDeltasMs: {},
      isTimedOut: false,
    },
    timeoutId: setTimeout(() => finalizePendingSwitch(true), FINALIZE_TIMEOUT_MS),
  };
};

/**
 * Record a milestone for the in-flight switch. First report wins; reports with
 * no switch in flight are ignored (e.g. data landing during normal use).
 *
 * Reporting `layout-restored` also schedules `first-paint-after-restore` via a
 * double `requestAnimationFrame` — an approximation of the first frame painted
 * with the new layout.
 */
export const markSwitchMilestone = (milestone: WsSwitchMilestone): void => {
  if (!isProfilerEnabled()) return;
  if (pendingSwitch === null) return;
  const { record } = pendingSwitch;
  if (record.milestoneDeltasMs[milestone] !== undefined) return;

  safeMark(`ws-switch.${milestone}`);
  record.milestoneDeltasMs[milestone] = performance.now() - record.startedAtMs;

  if (milestone === "layout-restored") {
    // Bind the scheduled callback to this record. If a new switch starts within
    // the two-frame window, `pendingSwitch` points at that switch's record, and
    // stamping first-paint onto it would cross-attribute the paint to the wrong
    // switch — so bail when the pending record is no longer the one we scheduled.
    const scheduledRecord = record;
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        if (pendingSwitch?.record !== scheduledRecord) return;
        markSwitchMilestone("first-paint-after-restore");
      });
    });
  }

  if (hasAllMilestones(record)) {
    finalizePendingSwitch(false);
  }
};
