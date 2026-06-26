import { PostHog } from "posthog-node";

import { getCurrentUserConfig } from "~/config/user_config";
import { EXECUTION_INSTANCE_ID } from "~/config/user_config";
import type { TelemetryEventName } from "~/telemetry/events";

// Consent-gated PostHog product analytics. Two hard guarantees:
//   1. capture() no-ops unless the user has granted genuine telemetry consent,
//      re-checked at send time (consent can change via /config/telemetry
//      between calls).
//   2. private content is masked before every send.
// The Python backend stopped reporting to PostHog; the backend has no token in
// practice, so without SCULPTOR_BACKEND_POSTHOG_TOKEN the client is never
// constructed and capture() is inert — preserving "no analytics" parity.

const POSTHOG_HOST = "https://us.i.posthog.com";
const BACKEND_POSTHOG_TOKEN_ENV = "SCULPTOR_BACKEND_POSTHOG_TOKEN";

// Keys whose values are private content (message bodies, paths, prompts,
// secrets). Matched case-insensitively against property keys at any depth.
const PRIVATE_KEY_PATTERN =
  /text|message|body|content|prompt|answer|diff|path|token|secret|password|api[_-]?key|email|cookie|authorization/i;

// Values that are private content regardless of the key they sit under. This is
// the backstop for payloads with arbitrary/unknown keys — notably the frontend
// trace batch, whose Chrome-trace `name` fields carry resource URLs and
// filesystem paths under a non-sensitive key. Matched against string leaves at
// any depth. Conservative on purpose: structural labels and short enum/version
// strings are kept so masking never silently drops legitimate analytics.
const SENSITIVE_VALUE_PATTERN = new RegExp(
  [
    "(?:https?|wss?|ftp|file)://", // URLs / URIs
    "(?:^|[\\s\"'(=,])(?:/[\\w.@%+~-]+){2,}", // absolute POSIX paths
    "[A-Za-z]:\\\\", // Windows drive paths
    "[\\w.+-]+@[\\w-]+\\.[\\w.-]+", // email addresses
    "\\b(?:sk|pk|ghp|gho|ghs|ghu|glpat|xox[abpr])[-_][A-Za-z0-9]{6,}", // token prefixes
    "\\bBearer\\s+\\S+", // bearer tokens
    "\\beyJ[\\w-]{8,}\\.[\\w-]{8,}", // JWTs
  ].join("|"),
  "i",
);
const REDACTED = "[redacted]";

// Recursively redact private values so raw content never reaches PostHog. Keys
// that match the private pattern are replaced with a marker; string leaves whose
// VALUE looks sensitive are redacted even under a non-matching key; everything
// else is kept (objects/arrays are walked).
export function maskProperties(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map((item) => maskProperties(item));
  }
  if (value !== null && typeof value === "object") {
    const out: Record<string, unknown> = {};
    for (const [key, inner] of Object.entries(value)) {
      out[key] = PRIVATE_KEY_PATTERN.test(key)
        ? REDACTED
        : maskProperties(inner);
    }
    return out;
  }
  if (typeof value === "string" && SENSITIVE_VALUE_PATTERN.test(value)) {
    return REDACTED;
  }
  return value;
}

// Genuine consent is required before any event is sent. The pre-onboarding
// anonymous default enables product analytics but leaves is_telemetry_level_set
// false, so keying on is_product_analytics_enabled alone would treat that
// un-consented default as consent. Both consent endpoints write
// is_telemetry_level_set alongside the analytics flag, so genuinely-consented
// events are unaffected by also requiring it here.
function consentGranted(): boolean {
  const config = getCurrentUserConfig();
  return (
    config.is_telemetry_level_set === true &&
    config.is_product_analytics_enabled === true
  );
}

let client: PostHog | null | undefined;

function getClient(): PostHog | null {
  if (client === undefined) {
    const token = process.env[BACKEND_POSTHOG_TOKEN_ENV];
    client =
      token !== undefined && token !== ""
        ? new PostHog(token, { host: POSTHOG_HOST })
        : null;
  }
  return client;
}

// Capture a product-analytics event. No-ops unless consent is granted (checked
// now, not at init) and a backend token is configured; masks props before send.
export function capture(
  event: TelemetryEventName,
  properties: Record<string, unknown> = {},
): void {
  if (!consentGranted()) {
    return;
  }
  const posthog = getClient();
  if (posthog === null) {
    return;
  }
  posthog.capture({
    distinctId: EXECUTION_INSTANCE_ID,
    event,
    properties: maskProperties(properties) as Record<string, unknown>,
  });
}

export async function shutdownTelemetry(): Promise<void> {
  if (client !== undefined && client !== null) {
    await client.shutdown();
  }
  client = undefined;
}

export function resetTelemetryForTests(): void {
  client = undefined;
}
