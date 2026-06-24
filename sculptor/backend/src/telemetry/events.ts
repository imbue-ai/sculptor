// The backend product-analytics event taxonomy. NOTE: the Python backend no
// longer reports to PostHog (SCU-1291) — telemetry is owned by the frontend,
// and the backend only serves TelemetryInfo. These names exist so the
// consent-gated capture path (telemetry/posthog.ts) is well-typed; no event
// fires unless a backend token is configured AND consent is granted.

export const TelemetryEvent = {
  // Frontend trace batches forwarded through the backend (Task 6.10/7.7).
  FrontendTraceBatch: "frontend_trace_batch",
} as const;

export type TelemetryEventName =
  (typeof TelemetryEvent)[keyof typeof TelemetryEvent];
