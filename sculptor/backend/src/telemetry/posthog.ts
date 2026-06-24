import { PostHog } from "posthog-node";

import { getCurrentUserConfig } from "~/config/user_config";
import { EXECUTION_INSTANCE_ID } from "~/config/user_config";
import type { TelemetryEventName } from "~/telemetry/events";

// Consent-gated PostHog product analytics (REQ-SEC-010). Two hard guarantees:
//   1. capture() no-ops unless is_product_analytics_enabled is set in the
//      config.toml UserConfig, RE-CHECKED at send time (consent can change via
//      /config/telemetry between calls).
//   2. private content is masked before every send.
// The Python backend stopped reporting to PostHog (SCU-1291); the backend has
// no token in practice, so without SCULPTOR_BACKEND_POSTHOG_TOKEN the client is
// never constructed and capture() is inert — preserving "no analytics" parity.

const POSTHOG_HOST = "https://us.i.posthog.com";
const BACKEND_POSTHOG_TOKEN_ENV = "SCULPTOR_BACKEND_POSTHOG_TOKEN";

// Keys whose values are private content (message bodies, paths, prompts,
// secrets). Matched case-insensitively against property keys at any depth.
const PRIVATE_KEY_PATTERN =
  /text|message|body|content|prompt|answer|diff|path|token|secret|password|api[_-]?key|email|cookie|authorization/i;
const REDACTED = "[redacted]";

// Recursively redact private values so raw content never reaches PostHog. Keys
// that match the private pattern are replaced with a marker; everything else is
// kept (objects/arrays are walked).
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
  return value;
}

function consentGranted(): boolean {
  return getCurrentUserConfig().is_product_analytics_enabled === true;
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
