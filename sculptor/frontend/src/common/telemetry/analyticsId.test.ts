import { describe, expect, it } from "vitest";

import { computeAnalyticsUserId, SCULPTOR_ANALYTICS_NAMESPACE } from "./analyticsId.ts";

describe("computeAnalyticsUserId", () => {
  // These snapshots lock in the namespace constant + email normalization rule.
  // Changing either of these UUIDs would mean every existing user maps to a
  // different analytics_user_id — splitting their event history permanently.
  // If a test here fails, do NOT update the expected value to match. See
  // `docs/development/posthog.md` for why this is load-bearing.
  it.each([
    ["alice@example.com", "5f3314ea-9569-5220-8fa6-f9f1430b113c"],
    ["bob@imbue.com", "483fe556-b06f-527b-ab9c-af466c50aadb"],
    ["carol@imbue.com", "7cb81f08-a599-5252-b835-2482fec73f67"],
  ])("returns the canonical UUID for %s", (email, expected) => {
    expect(computeAnalyticsUserId(email)).toBe(expected);
  });

  it("is deterministic — same email always produces the same UUID", () => {
    const email = "deterministic@example.com";
    expect(computeAnalyticsUserId(email)).toBe(computeAnalyticsUserId(email));
  });

  it("produces different UUIDs for different emails", () => {
    expect(computeAnalyticsUserId("a@example.com")).not.toBe(computeAnalyticsUserId("b@example.com"));
  });

  it("normalizes whitespace and case before hashing", () => {
    const canonical = computeAnalyticsUserId("alice@example.com");
    expect(computeAnalyticsUserId("  alice@example.com  ")).toBe(canonical);
    expect(computeAnalyticsUserId("Alice@Example.com")).toBe(canonical);
    expect(computeAnalyticsUserId("ALICE@EXAMPLE.COM")).toBe(canonical);
  });

  it("returns a UUID-shaped string", () => {
    expect(computeAnalyticsUserId("test@example.com")).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/,
    );
  });

  it("namespace constant has not been changed", () => {
    // Belt-and-suspenders against accidental namespace changes. The per-email
    // snapshots above would also catch this, but pinning the namespace value
    // directly makes the failure mode obvious in test output.
    expect(SCULPTOR_ANALYTICS_NAMESPACE).toBe("8bc0e99c-5ad5-5bea-bc65-c146afd28769");
  });
});
