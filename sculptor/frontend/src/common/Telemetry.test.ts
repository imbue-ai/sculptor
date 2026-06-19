import { posthog } from "posthog-js";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import type { TelemetryInfo, UserConfig } from "~/api";

import { computeAnalyticsUserId } from "./Analytics.ts";
import {
  applyTelemetryInfo,
  getTelemetryEnabled,
  identifyAnalyticsUser,
  initializeTelemetry,
  setTelemetryEnabled,
  updateTelemetryConfig,
} from "./Telemetry.ts";

const sentrySetUserMock = vi.fn();
const sentryAddIntegrationMock = vi.fn();
const replayStartBufferingMock = vi.fn();
const replayStopMock = vi.fn();
vi.mock("@sentry/react", () => ({
  setUser: (...args: Array<unknown>): unknown => sentrySetUserMock(...args),
  addIntegration: (...args: Array<unknown>): unknown => sentryAddIntegrationMock(...args),
  getReplay: (): unknown => ({
    startBuffering: (...args: Array<unknown>): unknown => replayStartBufferingMock(...args),
    stop: (...args: Array<unknown>): unknown => replayStopMock(...args),
  }),
}));

// Vite normally bakes these in via `define` (see `vite.electron.config.ts`).
// In jsdom they're undefined unless we stub them. The values themselves don't
// matter — `posthog.init` is mocked below — they just need to be non-empty so
// `initializeTelemetry()` takes the init branch instead of the early return.
beforeAll(() => {
  vi.stubGlobal("FRONTEND_POSTHOG_TOKEN", "phc_testing");
  vi.stubGlobal("FRONTEND_POSTHOG_HOST", "https://test.posthog.invalid");
  vi.spyOn(posthog, "init").mockImplementation(() => posthog as never);
  vi.spyOn(posthog, "register").mockImplementation(() => undefined as never);
  initializeTelemetry();
});

describe("identifyAnalyticsUser", () => {
  // Inferring spy types with `ReturnType<typeof vi.spyOn<...>>` trips up
  // TypeScript's check on vi.spyOn's key constraint for the `posthog`
  // singleton (the PostHog class type filter rejects method names like
  // "identify"). Use the simpler `ReturnType<typeof vi.spyOn>` for typing.
  let identifySpy: ReturnType<typeof vi.spyOn>;
  let setPersonPropertiesSpy: ReturnType<typeof vi.spyOn>;
  let getDistinctIdSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    identifySpy = vi.spyOn(posthog, "identify").mockImplementation(() => undefined as never);
    setPersonPropertiesSpy = vi.spyOn(posthog, "setPersonProperties").mockImplementation(() => undefined as never);
    // Default: posthog-js's auto-anonymous distinct_id (i.e. user not yet
    // identified). Individual tests override this for the warm-restart path.
    getDistinctIdSpy = vi.spyOn(posthog, "get_distinct_id").mockReturnValue("anonymous-distinct-id");
  });

  afterEach(() => {
    identifySpy.mockRestore();
    setPersonPropertiesSpy.mockRestore();
    getDistinctIdSpy.mockRestore();
  });

  it("calls posthog.identify with uuid5(NAMESPACE, email) and the email property", () => {
    const email = "alice@imbue.com";
    identifyAnalyticsUser(email);

    expect(identifySpy).toHaveBeenCalledTimes(1);
    expect(identifySpy).toHaveBeenCalledWith(computeAnalyticsUserId(email), { email });
    expect(setPersonPropertiesSpy).not.toHaveBeenCalled();
  });

  it("merges extra properties into the identify payload alongside email", () => {
    identifyAnalyticsUser("bob@imbue.com", { full_name: "Bob" });

    expect(identifySpy).toHaveBeenCalledWith(computeAnalyticsUserId("bob@imbue.com"), {
      email: "bob@imbue.com",
      full_name: "Bob",
    });
  });

  it("calls setPersonProperties instead of identify when distinct_id already matches (warm-restart path)", () => {
    // Simulate posthog-js's localStorage already holding the canonical UUID
    // from a previous session — calling identify again would fire a redundant
    // `$identify` merge event for the SDK to swallow.
    const email = "warm@imbue.com";
    getDistinctIdSpy.mockReturnValue(computeAnalyticsUserId(email));

    identifyAnalyticsUser(email, { full_name: "Warm User" });

    expect(setPersonPropertiesSpy).toHaveBeenCalledTimes(1);
    expect(setPersonPropertiesSpy).toHaveBeenCalledWith({
      email,
      full_name: "Warm User",
    });
    expect(identifySpy).not.toHaveBeenCalled();
  });

  it("normalizes email before identifying — same person across casing/whitespace variations", () => {
    identifyAnalyticsUser("Alice@Imbue.com");
    expect(identifySpy.mock.calls[0]?.[0]).toBe(computeAnalyticsUserId("alice@imbue.com"));
  });
});

function makeUserConfig(overrides: {
  isTelemetryEnabled: boolean;
  userEmail?: string;
  isErrorReportingEnabled?: boolean;
  isProductAnalyticsEnabled?: boolean;
}): UserConfig {
  const isTelemetryOn = overrides.isTelemetryEnabled;
  return {
    userEmail: overrides.userEmail ?? "alice@imbue.com",
    userId: "user_123",
    organizationId: "org_123",
    instanceId: "instance_123",
    isErrorReportingEnabled: overrides.isErrorReportingEnabled ?? isTelemetryOn,
    isProductAnalyticsEnabled: overrides.isProductAnalyticsEnabled ?? isTelemetryOn,
    isSessionRecordingEnabled: false,
  } as unknown as UserConfig;
}

function makeTelemetryInfo(userConfig: UserConfig): TelemetryInfo {
  return {
    userConfig,
    sculptorVersion: "0.0.0",
    sculptorExecutionInstanceId: "exec_123",
  } as unknown as TelemetryInfo;
}

describe("telemetry consent reconciliation", () => {
  let optInSpy: ReturnType<typeof vi.spyOn>;
  let optOutSpy: ReturnType<typeof vi.spyOn>;
  let setConfigSpy: ReturnType<typeof vi.spyOn>;
  let registerSpy: ReturnType<typeof vi.spyOn>;
  let identifySpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    sentrySetUserMock.mockClear();
    sentryAddIntegrationMock.mockClear();
    replayStartBufferingMock.mockClear();
    replayStopMock.mockClear();
    optInSpy = vi.spyOn(posthog, "opt_in_capturing").mockImplementation(() => undefined as never);
    optOutSpy = vi.spyOn(posthog, "opt_out_capturing").mockImplementation(() => undefined as never);
    setConfigSpy = vi.spyOn(posthog, "set_config").mockImplementation(() => undefined as never);
    registerSpy = vi.spyOn(posthog, "register").mockImplementation(() => undefined as never);
    identifySpy = vi.spyOn(posthog, "identify").mockImplementation(() => undefined as never);
    vi.spyOn(posthog, "get_distinct_id").mockReturnValue("anonymous-distinct-id");
    vi.spyOn(posthog, "sentryIntegration").mockImplementation(() => ({}) as never);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    setTelemetryEnabled(true);
  });

  describe("applyTelemetryInfo", () => {
    it("opts in, identifies, sets the Sentry user, and arms replay buffering when telemetry is on", () => {
      applyTelemetryInfo(makeTelemetryInfo(makeUserConfig({ isTelemetryEnabled: true })));

      expect(optInSpy).toHaveBeenCalledTimes(1);
      // The recurring opt-in must be silent — no `$opt_in` meta event on
      // every handshake.
      expect(optInSpy).toHaveBeenCalledWith({ captureEventName: null });
      expect(optOutSpy).not.toHaveBeenCalled();
      expect(sentrySetUserMock).toHaveBeenCalledTimes(1);
      expect(sentrySetUserMock.mock.calls[0]?.[0]).toMatchObject({ email: "alice@imbue.com" });
      expect(replayStartBufferingMock).toHaveBeenCalledTimes(1);
      expect(replayStopMock).not.toHaveBeenCalled();
      expect(setConfigSpy).toHaveBeenCalled();
      expect(registerSpy).toHaveBeenCalled();
      expect(sentryAddIntegrationMock).toHaveBeenCalled();
      expect(getTelemetryEnabled()).toBe(true);
    });

    it("opts out, clears the Sentry user, stops replay, and skips the PostHog→Sentry integration when telemetry is off", () => {
      applyTelemetryInfo(makeTelemetryInfo(makeUserConfig({ isTelemetryEnabled: false })));

      expect(optOutSpy).toHaveBeenCalledTimes(1);
      expect(optInSpy).not.toHaveBeenCalled();
      expect(sentrySetUserMock).toHaveBeenCalledWith(null);
      expect(replayStopMock).toHaveBeenCalledTimes(1);
      expect(replayStartBufferingMock).not.toHaveBeenCalled();
      expect(sentryAddIntegrationMock).not.toHaveBeenCalled();
      expect(getTelemetryEnabled()).toBe(false);
    });
  });

  describe("updateTelemetryConfig", () => {
    it("opts in and sets the Sentry user when telemetry is on", () => {
      updateTelemetryConfig(makeTelemetryInfo(makeUserConfig({ isTelemetryEnabled: true })));

      expect(optInSpy).toHaveBeenCalledTimes(1);
      expect(optOutSpy).not.toHaveBeenCalled();
      expect(sentrySetUserMock.mock.calls[0]?.[0]).toMatchObject({ email: "alice@imbue.com" });
      expect(getTelemetryEnabled()).toBe(true);
    });

    it("opts out and clears the Sentry user when telemetry is off", () => {
      updateTelemetryConfig(makeTelemetryInfo(makeUserConfig({ isTelemetryEnabled: false })));

      expect(optOutSpy).toHaveBeenCalledTimes(1);
      expect(optInSpy).not.toHaveBeenCalled();
      expect(sentrySetUserMock).toHaveBeenCalledWith(null);
      expect(getTelemetryEnabled()).toBe(false);
    });
  });

  describe("legacy mixed-flag configs", () => {
    // The consent endpoints always write the flags together and the backend
    // normalizes mixed (hand-edited / legacy) configs to all-off on load.
    // The frontend AND is defense-in-depth with the same conservative bias:
    // a mixed config must never enable anything.
    it("treats a config with only error reporting enabled as fully disabled", () => {
      applyTelemetryInfo(
        makeTelemetryInfo(makeUserConfig({ isTelemetryEnabled: true, isProductAnalyticsEnabled: false })),
      );

      expect(getTelemetryEnabled()).toBe(false);
      expect(optOutSpy).toHaveBeenCalledTimes(1);
      expect(optInSpy).not.toHaveBeenCalled();
      expect(replayStopMock).toHaveBeenCalledTimes(1);
      expect(replayStartBufferingMock).not.toHaveBeenCalled();
      expect(sentrySetUserMock).toHaveBeenCalledWith(null);
      expect(identifySpy).not.toHaveBeenCalled();
    });
  });

  describe("opt-out persistence", () => {
    it("mirrors the opt-out in localStorage so the next launch respects it pre-handshake", () => {
      setTelemetryEnabled(false);
      expect(window.localStorage.getItem("sculptor.telemetryOptedOut")).toBe("true");

      setTelemetryEnabled(true);
      expect(window.localStorage.getItem("sculptor.telemetryOptedOut")).toBeNull();
    });
  });
});
