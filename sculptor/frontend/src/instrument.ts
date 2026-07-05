import * as Sentry from "@sentry/react";

import { getTelemetryEnabled } from "~/common/telemetry/telemetry.ts";

declare const FRONTEND_SENTRY_DSN: string;
declare const FRONTEND_SENTRY_RELEASE_ID: string;

/**
 * Drops background events when telemetry is off. Always lets feedback events
 * through so the Report a Problem flow keeps working with telemetry opted
 * out — those are user-initiated, one-shot sends.
 *
 * Session Replay uploads do NOT pass through beforeSend; the recorder is
 * stopped/started in `Telemetry.ts::reconcileTelemetryConsent`.
 *
 * Exported for unit-test access. Sentry only sees this via the `beforeSend`
 * option in `Sentry.init`.
 */
export const filterSentryEventByTelemetryConsent = <T extends { type?: string }>(event: T): T | null => {
  if (event.type === "feedback") return event;
  if (!getTelemetryEnabled()) return null;
  return event;
};

export const initializeSentry = (): void => {
  if (!FRONTEND_SENTRY_DSN || FRONTEND_SENTRY_DSN === "") {
    console.log("Sentry DSN not configured, skipping initialization");
    return;
  }

  console.log(`Initializing Sentry with DSN: ${FRONTEND_SENTRY_DSN} and release ID: ${FRONTEND_SENTRY_RELEASE_ID}`);

  Sentry.init({
    dsn: FRONTEND_SENTRY_DSN,
    integrations: [
      Sentry.captureConsoleIntegration({
        levels: ["error", "warn"],
        // Sentry 9+ marks console-captured events as handled by default,
        // which would re-group existing issues; keep the pre-upgrade
        // unhandled classification.
        handled: false,
      }),
      Sentry.contextLinesIntegration(),
      Sentry.extraErrorDataIntegration(),
      // FIXME: turn this back on, but only once we make custom HTTP error codes for the places where we currently return 500
      // Sentry.httpClientIntegration(),
      // disabling all masking for now
      Sentry.replayIntegration({
        maskAllText: false,
        maskAllInputs: false,
        blockAllMedia: false,
      }),
      Sentry.feedbackIntegration({
        autoInject: false,
      }),
    ],
    // Performance tracing disabled (SCU-1347): unused and noisy (SCU-1346).
    tracesSampleRate: 0,
    // Replays never upload on their own: both sample rates stay 0 and the
    // recorder runs in manually-started buffer mode (below), which keeps the
    // last ~60s in memory and uploads only when the user submits a bug
    // report (see `submitReportAtom`).
    replaysSessionSampleRate: 0,
    replaysOnErrorSampleRate: 0,
    environment: import.meta.env.MODE,
    release: FRONTEND_SENTRY_RELEASE_ID,
    beforeSend: filterSentryEventByTelemetryConsent,
  });

  // For opted-out users (persisted across restarts), don't record at all. An
  // opt-in mid-session arms the buffer via the consent reconciliation in
  // Telemetry.ts.
  if (getTelemetryEnabled()) {
    Sentry.getReplay()?.startBuffering();
  }
};
