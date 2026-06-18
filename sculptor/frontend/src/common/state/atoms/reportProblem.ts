import * as Sentry from "@sentry/react";
import type { WritableAtom } from "jotai";
import { atom } from "jotai";

import type { HealthCheckResponse } from "~/api";
import { uploadDiagnostics } from "~/api";
import { getTelemetryEnabled } from "~/common/Telemetry.ts";

import { healthCheckDataAtom } from "./backend.ts";
import { userEmailAtom, userFullNameAtom } from "./userConfig.ts";

export type SubmitState =
  | { type: "idle" }
  | { type: "collecting" }
  | { type: "reporting" }
  | { type: "success"; reportId: string | null; sentryEventId: string; didDiagnosticsFail: boolean }
  | { type: "error"; message: string };

export type ScreenshotState = "idle" | "capturing" | "captured" | "failed";

export type ReportProblemState = {
  isOpen: boolean;
  description: string;
  shouldIncludeLogs: boolean;
  isDiagnosticsExpanded: boolean;
  submitState: SubmitState;
  screenshotState: ScreenshotState;
  screenshotData: Uint8Array | null;
  copiedField: "reference" | null;
};

export type DiagnosticEntry = {
  label: string;
  value: string | undefined;
};

const formatUptime = (seconds: number | undefined): string => {
  if (seconds === undefined) return "\u2014";
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
};

const formatDiskSpace = (gb: number | undefined): string => {
  if (gb === undefined) return "\u2014";
  return `${gb.toFixed(1)} GB`;
};

export const getDiagnosticEntries = (data: HealthCheckResponse): ReadonlyArray<DiagnosticEntry> => [
  { label: "Version", value: data.version },
  { label: "Git SHA", value: data.gitSha },
  { label: "Platform", value: `${data.platform} ${data.platformVersion}` },
  { label: "Install Mode", value: data.installMode },
  { label: "Install Path", value: data.installPath },
  { label: "Free Disk", value: formatDiskSpace(data.freeDiskGb) },
  { label: "Uptime", value: formatUptime(data.uptimeSeconds) },
  { label: "Active Agents", value: data.activeTaskCount?.toString() },
  { label: "Data Directory", value: data.dataDirectory },
  { label: "Claude CLI", value: data.dependenciesStatus?.claude?.version ?? undefined },
  { label: "Claude Path", value: data.dependenciesStatus?.claude?.path ?? undefined },
  { label: "Claude Mode", value: data.dependenciesStatus?.claude?.mode ?? undefined },
  { label: "URL", value: window.location.href },
  ...(data.ciJobId ? [{ label: "CI Job", value: data.ciJobId }] : []),
  ...(data.ciRef ? [{ label: "CI Ref", value: data.ciRef }] : []),
];

export const formatDiagnosticsAsText = (entries: ReadonlyArray<DiagnosticEntry>): string =>
  entries.map(({ label, value }) => `${label}: ${value ?? "\u2014"}`).join("\n");

/** Subset of diagnostic labels promoted to Sentry tags (keys must be <=32 chars, alphanumeric/._-). */
const DIAGNOSTIC_TAG_KEYS: Readonly<Record<string, string>> = {
  "Install Path": "install_path",
  "Install Mode": "install_mode",
  Platform: "platform",
  "Claude Mode": "claude_mode",
  "Claude CLI": "claude_cli_version",
};

const getDiagnosticTags = (entries: ReadonlyArray<DiagnosticEntry>): Record<string, string> => {
  const tags: Record<string, string> = {};
  for (const { label, value } of entries) {
    const key = DIAGNOSTIC_TAG_KEYS[label];
    if (key !== undefined && value !== undefined) {
      tags[key] = value;
    }
  }
  return tags;
};

const DEFAULT_STATE: ReportProblemState = {
  isOpen: false,
  description: "",
  // The uploaded logs are the full TRACE-level server log plus the electron
  // log — they can carry repo paths, branch names, and other user content,
  // so including them is opt-in, not the default.
  shouldIncludeLogs: false,
  isDiagnosticsExpanded: false,
  submitState: { type: "idle" },
  screenshotState: "idle",
  screenshotData: null,
  copiedField: null,
};

export const reportProblemAtom = atom<ReportProblemState>(DEFAULT_STATE);

/** Updater that merges a partial state into the current report problem state. */
export const updateReportProblemAtom: WritableAtom<null, [Partial<ReportProblemState>], void> = atom(
  null,
  (get, set, update: Partial<ReportProblemState>) => {
    set(reportProblemAtom, { ...get(reportProblemAtom), ...update });
  },
);

/** Resets the form fields but preserves the open/close state. */
export const resetReportProblemFormAtom: WritableAtom<null, [], void> = atom(null, (get, set) => {
  set(reportProblemAtom, {
    ...DEFAULT_STATE,
    isOpen: get(reportProblemAtom).isOpen,
  });
});

/**
 * Write-only atom that runs the full submit flow:
 * 1. Upload diagnostics to S3 (if logs checkbox is checked)
 * 2. Send feedback to Sentry
 *
 * The flow runs to completion even if the popover is closed or the component
 * unmounts — the atom store holds the state independently of the React tree.
 */
export const submitReportAtom: WritableAtom<null, [], Promise<void>> = atom(null, async (get, set) => {
  const state = get(reportProblemAtom);
  const { description, shouldIncludeLogs } = state;
  const userEmail = get(userEmailAtom);
  const userFullName = get(userFullNameAtom);

  let reportId: string | null = null;
  let s3Url: string | null = null;
  let didDiagnosticsFail = false;

  if (shouldIncludeLogs) {
    set(updateReportProblemAtom, { submitState: { type: "collecting" } });
    try {
      const { data } = await uploadDiagnostics({
        body: {
          description,
          currentUrl: window.location.href,
        },
        meta: { skipWsAck: true },
      });
      reportId = data.reportId;
      s3Url = data.s3Url;
    } catch {
      didDiagnosticsFail = true;
    }
  }

  set(updateReportProblemAtom, { submitState: { type: "reporting" } });
  try {
    // With no Sentry DSN there's no client, so captureFeedback no-ops yet still
    // returns an id — making the report look sent. Fail honestly instead.
    if (Sentry.getClient() === undefined) {
      throw new Error("Error reporting isn't configured in this build, so the report couldn't be sent.");
    }

    const { screenshotData } = get(reportProblemAtom);
    const healthCheckData = get(healthCheckDataAtom);
    const attachments: Array<{ filename: string; data: Uint8Array; contentType: string }> = [];
    if (screenshotData !== null) {
      attachments.push({ filename: "screenshot.png", data: screenshotData, contentType: "image/png" });
    }

    // Build diagnostic tags and context from health check data.
    let diagnosticTags: Record<string, string> = {};
    let diagnosticsContext: Record<string, string> | null = null;
    if (healthCheckData !== null) {
      const entries = getDiagnosticEntries(healthCheckData);
      diagnosticTags = getDiagnosticTags(entries);
      diagnosticsContext = Object.fromEntries(
        entries.filter(({ value }) => value !== undefined).map(({ label, value }) => [label, value!]),
      );
    }

    // Extract the fragment (our SPA route) since the base URL is always the same.
    const page = window.location.hash.replace(/^#/, "") || undefined;

    const sentryEventId = Sentry.withScope((scope) => {
      if (diagnosticsContext !== null) {
        scope.setContext("diagnostics", diagnosticsContext);
      }
      return Sentry.captureFeedback(
        {
          message: description || "(no description)",
          url: window.location.href,
          // Attach identity explicitly: feedback must stay followable even
          // when telemetry is off and the Sentry user scope is cleared.
          email: userEmail,
          name: userFullName,
          tags: {
            ...(reportId !== null ? { "report.id": reportId } : {}),
            ...(s3Url !== null ? { "report.s3Url": s3Url } : {}),
            ...(didDiagnosticsFail ? { "report.diagnosticsFailed": "true" } : {}),
            ...(page !== undefined ? { page } : {}),
            ...diagnosticTags,
          },
        },
        { attachments },
      );
    });
    set(updateReportProblemAtom, {
      submitState: { type: "success", reportId, sentryEventId, didDiagnosticsFail },
    });

    // Capturing the feedback made the replay integration flush the buffered
    // last ~60s and link it via contexts.feedback.replay_id — but that flush
    // also converts the recorder to continuous session mode. Wait for it to
    // settle, then stop and re-arm buffering, so replays only ever upload
    // around a submitted report.
    const replay = Sentry.getReplay();
    if (replay !== undefined && getTelemetryEnabled()) {
      try {
        await replay.flush();
        await replay.stop();
        replay.startBuffering();
      } catch {
        // Replay re-arming is best-effort; the report itself already went out.
      }
    }
  } catch (error) {
    set(updateReportProblemAtom, { submitState: { type: "error", message: String(error) } });
  }
});
