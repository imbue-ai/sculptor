import { Theme } from "@radix-ui/themes";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import type { UserConfig } from "~/api";
import { ElementIds } from "~/api";
import { userConfigAtom } from "~/common/state/atoms/userConfig.ts";
import { getTelemetryEnabled, initializeTelemetry, setTelemetryEnabled } from "~/common/Telemetry.ts";

import { ToastType } from "../../../components/Toast.tsx";
import { TelemetryRow } from "./TelemetryRow.tsx";

const { mockSetTelemetry, mockOptIn, mockOptOut, mockCapture, mockSentrySetUser } = vi.hoisted(() => ({
  mockSetTelemetry: vi.fn(),
  mockOptIn: vi.fn(),
  mockOptOut: vi.fn(),
  mockCapture: vi.fn(),
  mockSentrySetUser: vi.fn(),
}));

vi.mock("~/api", async (importOriginal) => {
  const actual = await importOriginal();
  return {
    ...(actual as object),
    setTelemetry: mockSetTelemetry,
  };
});

vi.mock("posthog-js", () => ({
  posthog: {
    init: vi.fn(),
    opt_in_capturing: mockOptIn,
    opt_out_capturing: mockOptOut,
    capture: mockCapture,
  },
}));

vi.mock("@sentry/react", () => ({
  setUser: mockSentrySetUser,
  getReplay: (): unknown => undefined,
}));

// applyTelemetryConsent only reconciles PostHog once Telemetry.ts considers
// itself initialized; the mocked posthog.init makes this a no-op SDK-wise.
beforeAll(() => {
  vi.stubGlobal("FRONTEND_POSTHOG_TOKEN", "phc_testing");
  vi.stubGlobal("FRONTEND_POSTHOG_HOST", "https://test.posthog.invalid");
  initializeTelemetry();
});

const makeUserConfig = (isTelemetryOn: boolean): UserConfig =>
  ({
    userEmail: "alice@imbue.com",
    userId: "user_123",
    organizationId: "org_123",
    instanceId: "instance_123",
    isErrorReportingEnabled: isTelemetryOn,
    isProductAnalyticsEnabled: isTelemetryOn,
    isSessionRecordingEnabled: false,
  }) as unknown as UserConfig;

const renderTelemetryRow = (
  isTelemetryOn: boolean,
  setToast: (toast: Parameters<Parameters<typeof TelemetryRow>[0]["setToast"]>[0]) => void,
): void => {
  const store = createStore();
  store.set(userConfigAtom, makeUserConfig(isTelemetryOn));
  setTelemetryEnabled(isTelemetryOn);

  const Wrapper = ({ children }: { children: ReactNode }): ReactElement => (
    <Theme>
      <Provider store={store}>{children}</Provider>
    </Theme>
  );

  render(<TelemetryRow setToast={setToast} />, { wrapper: Wrapper });
};

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  // Reset the module-level flag to its default for the next test.
  setTelemetryEnabled(true);
});

describe("TelemetryRow opt-out", () => {
  let setToast: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    setToast = vi.fn();
  });

  it("fires the meta event, flips the SDKs, and persists via POST", async () => {
    mockSetTelemetry.mockResolvedValueOnce({ data: makeUserConfig(false) });
    renderTelemetryRow(true, setToast);

    fireEvent.click(screen.getByTestId(ElementIds.SETTINGS_PRIVACY_TELEMETRY_SWITCH));
    const confirmButton = await screen.findByTestId(ElementIds.SETTINGS_PRIVACY_TELEMETRY_DIALOG_CONFIRM);
    fireEvent.click(confirmButton);

    await waitFor(() => {
      expect(mockSetTelemetry).toHaveBeenCalledTimes(1);
    });

    // The meta event fires before the opt-out flip — afterwards PostHog
    // would drop it.
    expect(mockCapture).toHaveBeenCalledWith("telemetry_opted_out");
    expect(mockCapture.mock.invocationCallOrder[0]).toBeLessThan(mockOptOut.mock.invocationCallOrder[0] ?? Infinity);
    expect(mockOptOut).toHaveBeenCalledTimes(1);
    expect(getTelemetryEnabled()).toBe(false);
    expect(mockSentrySetUser).toHaveBeenLastCalledWith(null);
    expect(setToast).not.toHaveBeenCalled();
    await waitFor(() => {
      expect(screen.queryByTestId(ElementIds.SETTINGS_PRIVACY_TELEMETRY_DIALOG)).toBeNull();
    });
  });

  it("surfaces the error toast and rolls back the telemetry state on POST failure", async () => {
    mockSetTelemetry.mockRejectedValueOnce(new Error("network down"));
    renderTelemetryRow(true, setToast);

    fireEvent.click(screen.getByTestId(ElementIds.SETTINGS_PRIVACY_TELEMETRY_SWITCH));
    const confirmButton = await screen.findByTestId(ElementIds.SETTINGS_PRIVACY_TELEMETRY_DIALOG_CONFIRM);
    fireEvent.click(confirmButton);

    await waitFor(() => {
      expect(setToast).toHaveBeenCalledTimes(1);
    });

    expect(setToast).toHaveBeenCalledWith({
      type: ToastType.ERROR_PROMINENT,
      title: "Couldn't disable telemetry",
      description: "Please try again.",
    });
    // Rollback: telemetry flag back to true, PostHog opt-in restored, Sentry
    // user re-set (opt_out_capturing ran before the rollback, so PostHog saw
    // both calls).
    expect(getTelemetryEnabled()).toBe(true);
    expect(mockOptOut).toHaveBeenCalledTimes(1);
    expect(mockOptIn).toHaveBeenCalledTimes(1);
    const sentryCalls = mockSentrySetUser.mock.calls;
    expect(sentryCalls[sentryCalls.length - 1]?.[0]).toMatchObject({ email: "alice@imbue.com" });
    // The dialog closes on failure, just as it would on success.
    await waitFor(() => {
      expect(screen.queryByTestId(ElementIds.SETTINGS_PRIVACY_TELEMETRY_DIALOG)).toBeNull();
    });
  });
});

describe("TelemetryRow opt-in", () => {
  let setToast: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    setToast = vi.fn();
  });

  it("flips the SDKs without a confirmation dialog and fires the meta event after the POST", async () => {
    mockSetTelemetry.mockResolvedValueOnce({ data: makeUserConfig(true) });
    renderTelemetryRow(false, setToast);

    fireEvent.click(screen.getByTestId(ElementIds.SETTINGS_PRIVACY_TELEMETRY_SWITCH));

    await waitFor(() => {
      expect(mockCapture).toHaveBeenCalledWith("telemetry_opted_in");
    });

    expect(screen.queryByTestId(ElementIds.SETTINGS_PRIVACY_TELEMETRY_DIALOG)).toBeNull();
    expect(mockOptIn).toHaveBeenCalledTimes(1);
    expect(getTelemetryEnabled()).toBe(true);
    expect(mockSentrySetUser).toHaveBeenLastCalledWith(expect.objectContaining({ email: "alice@imbue.com" }));
    expect(setToast).not.toHaveBeenCalled();
  });

  it("disables the switch while the POST is in flight so a second click can't fire a concurrent flip", async () => {
    let resolvePost: (value: unknown) => void = () => undefined;
    mockSetTelemetry.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolvePost = resolve;
        }),
    );
    renderTelemetryRow(false, setToast);

    const telemetrySwitch = screen.getByTestId(ElementIds.SETTINGS_PRIVACY_TELEMETRY_SWITCH);
    fireEvent.click(telemetrySwitch);

    await waitFor(() => {
      expect(telemetrySwitch).toBeDisabled();
    });
    fireEvent.click(telemetrySwitch);
    expect(mockSetTelemetry).toHaveBeenCalledTimes(1);

    resolvePost({ data: makeUserConfig(true) });
    await waitFor(() => {
      expect(telemetrySwitch).not.toBeDisabled();
    });
  });

  it("surfaces the error toast and rolls back the telemetry state on POST failure", async () => {
    mockSetTelemetry.mockRejectedValueOnce(new Error("network down"));
    renderTelemetryRow(false, setToast);

    fireEvent.click(screen.getByTestId(ElementIds.SETTINGS_PRIVACY_TELEMETRY_SWITCH));

    await waitFor(() => {
      expect(setToast).toHaveBeenCalledTimes(1);
    });

    expect(setToast).toHaveBeenCalledWith({
      type: ToastType.ERROR_PROMINENT,
      title: "Couldn't enable telemetry",
      description: "Please try again.",
    });
    // Rollback: telemetry flag back to false, PostHog opt-out restored,
    // Sentry user cleared.
    expect(getTelemetryEnabled()).toBe(false);
    expect(mockOptIn).toHaveBeenCalledTimes(1);
    expect(mockOptOut).toHaveBeenCalledTimes(1);
    expect(mockSentrySetUser).toHaveBeenLastCalledWith(null);
  });
});
