/**
 * Analytics identity helpers for PostHog telemetry.
 *
 * The user identity model used by Sculptor's analytics is:
 *   analytics_user_id = uuid5(SCULPTOR_ANALYTICS_NAMESPACE, email)
 *
 * Same email always produces the same UUID, regardless of which install or
 * machine it's computed on. That's how we get cross-install user unification
 * without relying on PostHog's alias machinery.
 *
 * IMPORTANT: SCULPTOR_ANALYTICS_NAMESPACE must NEVER change. Changing it would
 * permanently break cross-install unification: every existing user would map to
 * a new analytics_user_id, splitting their event history. See `docs/development/posthog.md`.
 */

import { v5 as uuidv5 } from "uuid";

// Derived deterministically from the built-in DNS namespace and our domain.
// uuidv5 is a pure function — this value is identical every time the module
// loads and matches Python's `uuid.uuid5(uuid.NAMESPACE_DNS, "sculptor.imbue.com")`.
// Snapshot tests in Analytics.test.ts pin the resulting value so accidental
// changes to either input here fail loudly.
export const SCULPTOR_ANALYTICS_NAMESPACE = uuidv5("sculptor.imbue.com", uuidv5.DNS);

/**
 * Compute the canonical analytics user ID for an email address.
 *
 * Email is normalized (trimmed + lowercased) before hashing so trivial
 * variations don't fragment identity.
 */
export function computeAnalyticsUserId(email: string): string {
  const normalized = email.trim().toLowerCase();
  return uuidv5(normalized, SCULPTOR_ANALYTICS_NAMESPACE);
}
