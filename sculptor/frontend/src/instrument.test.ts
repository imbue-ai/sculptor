import { afterEach, describe, expect, it } from "vitest";

import { setTelemetryEnabled } from "~/common/Telemetry.ts";

import { filterSentryEventByTelemetryConsent } from "./instrument.ts";

describe("filterSentryEventByTelemetryConsent", () => {
  afterEach(() => {
    setTelemetryEnabled(true);
  });

  it("drops exception events when telemetry is off", () => {
    setTelemetryEnabled(false);
    const event = { type: undefined };
    expect(filterSentryEventByTelemetryConsent(event)).toBeNull();
  });

  it("allows exception events when telemetry is on", () => {
    setTelemetryEnabled(true);
    const event = { type: undefined };
    expect(filterSentryEventByTelemetryConsent(event)).toBe(event);
  });

  it("allows feedback events when telemetry is off — Report a Problem keeps working", () => {
    setTelemetryEnabled(false);
    const event = { type: "feedback" };
    expect(filterSentryEventByTelemetryConsent(event)).toBe(event);
  });

  it("allows feedback events when telemetry is on", () => {
    setTelemetryEnabled(true);
    const event = { type: "feedback" };
    expect(filterSentryEventByTelemetryConsent(event)).toBe(event);
  });
});
