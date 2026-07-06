import { Theme } from "@radix-ui/themes";
import { act, cleanup, render, screen } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { HealthCheckResponse } from "~/api";
import { backendStatusAtom } from "~/common/state/atoms/backend.ts";

import { BackendStatusBoundary } from "./BackendStatusBoundary.tsx";

const { mockGetHealthCheck } = vi.hoisted(() => ({
  mockGetHealthCheck: vi.fn(),
}));

vi.mock("~/api", async (importOriginal) => {
  const original = await importOriginal();
  return {
    ...(original as object),
    getHealthCheck: mockGetHealthCheck,
  };
});

type Store = ReturnType<typeof createStore>;

const HEALTHY_RESPONSE = {
  data: {
    freeDiskGb: 100,
    minFreeDiskGb: 5,
    freeDiskGbWarnLimit: 10,
  } as unknown as HealthCheckResponse,
};

// Mirrors HEALTH_CHECK_INTERVAL_MS in BackendStatusBoundary.tsx.
const POLL_INTERVAL_MS = 3_000;

// Backdoors the mock and the jsdom document between polls; the component reads
// both on every check, so flipping these mid-test simulates the backend dying
// or the app being backgrounded.
let isBackendHealthy = true;
let isDocumentHidden = false;

const renderBoundary = (): Store => {
  const store = createStore();
  const Wrapper = ({ children }: { children: ReactNode }): ReactElement => (
    <Provider store={store}>
      <Theme>{children}</Theme>
    </Provider>
  );
  render(
    <BackendStatusBoundary>
      <div data-testid="app-content" />
    </BackendStatusBoundary>,
    { wrapper: Wrapper },
  );
  return store;
};

// Flushes pending microtasks (in-flight health check promises) without
// advancing the poll interval.
const flushMicrotasks = async (): Promise<void> => {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(0);
  });
};

// Advances time by one poll interval and settles the resulting health check.
const advanceOnePoll = async (): Promise<void> => {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
  });
};

// Renders the boundary and settles the initial successful health check, so
// tests start from the steady "running" state the way a live session would.
const renderRunningBoundary = async (): Promise<Store> => {
  const store = renderBoundary();
  await flushMicrotasks();
  expect(store.get(backendStatusAtom).status).toBe("running");
  return store;
};

beforeEach(() => {
  vi.useFakeTimers();
  isBackendHealthy = true;
  isDocumentHidden = false;
  mockGetHealthCheck.mockReset();
  mockGetHealthCheck.mockImplementation(() =>
    isBackendHealthy ? Promise.resolve(HEALTHY_RESPONSE) : Promise.reject(new Error("connection refused")),
  );
  Object.defineProperty(document, "hidden", {
    configurable: true,
    get: () => isDocumentHidden,
  });
});

afterEach(() => {
  cleanup();
  // Remove the instance-level accessor so the prototype getter is restored.
  Reflect.deleteProperty(document, "hidden");
  vi.useRealTimers();
});

describe("BackendStatusBoundary health-check escalation", () => {
  // Timeline note: entering "reconnecting" re-runs the status-keyed effect,
  // which fires one immediate retry on top of the interval poll. So the 5th
  // consecutive failure lands on the 4th poll after the backend goes down.
  it("softens the first failures to reconnecting and only escalates to unresponsive after sustained failure", async () => {
    const store = await renderRunningBoundary();
    isBackendHealthy = false;

    await advanceOnePoll(); // failure 1 + the immediate retry (failure 2)
    expect(store.get(backendStatusAtom).status).toBe("reconnecting");
    expect(store.get(backendStatusAtom).payload.message).not.toMatch(/restart/i);
    // The app stays mounted behind the soft banner.
    expect(screen.getByTestId("app-content")).toBeTruthy();

    await advanceOnePoll(); // failure 3
    await advanceOnePoll(); // failure 4
    expect(store.get(backendStatusAtom).status).toBe("reconnecting");

    await advanceOnePoll(); // failure 5 crosses the threshold
    expect(store.get(backendStatusAtom).status).toBe("unresponsive");
    expect(store.get(backendStatusAtom).payload.message).toMatch(/restart/i);
  });

  it("returns to running on a successful check and resets the failure count", async () => {
    const store = await renderRunningBoundary();

    isBackendHealthy = false;
    await advanceOnePoll();
    await advanceOnePoll();
    expect(store.get(backendStatusAtom).status).toBe("reconnecting");

    isBackendHealthy = true;
    await advanceOnePoll();
    expect(store.get(backendStatusAtom).status).toBe("running");

    // After the reset, the outage clock starts over: were the counter stale,
    // this first failed poll would already cross the threshold.
    isBackendHealthy = false;
    await advanceOnePoll();
    expect(store.get(backendStatusAtom).status).toBe("reconnecting");
    await advanceOnePoll();
    await advanceOnePoll();
    expect(store.get(backendStatusAtom).status).toBe("reconnecting");
    await advanceOnePoll();
    expect(store.get(backendStatusAtom).status).toBe("unresponsive");
  });

  it("does not poll or change status while the document is hidden", async () => {
    const store = await renderRunningBoundary();
    isDocumentHidden = true;
    isBackendHealthy = false;
    const callsBeforeHidden = mockGetHealthCheck.mock.calls.length;

    for (let i = 0; i < 6; i++) {
      await advanceOnePoll();
    }

    expect(mockGetHealthCheck.mock.calls.length).toBe(callsBeforeHidden);
    expect(store.get(backendStatusAtom).status).toBe("running");
  });

  it("health-checks immediately on becoming visible and shows reconnecting on a post-resume failure", async () => {
    const store = await renderRunningBoundary();
    isDocumentHidden = true;
    isBackendHealthy = false;
    await advanceOnePoll();

    isDocumentHidden = false;
    const callsBeforeResume = mockGetHealthCheck.mock.calls.length;
    await act(async () => {
      document.dispatchEvent(new Event("visibilitychange"));
      await vi.advanceTimersByTimeAsync(0);
    });

    // The resume check fires without waiting for the next poll tick...
    expect(mockGetHealthCheck.mock.calls.length).toBeGreaterThan(callsBeforeResume);
    // ...and its failure surfaces as the soft state, not the red banner.
    expect(store.get(backendStatusAtom).status).toBe("reconnecting");
  });

  it("ignores a check that fails after the app is hidden mid-flight", async () => {
    const store = await renderRunningBoundary();

    let rejectInFlight: (error: Error) => void = () => {};
    mockGetHealthCheck.mockImplementationOnce(
      () =>
        new Promise((_resolve, reject) => {
          rejectInFlight = reject;
        }),
    );
    await advanceOnePoll(); // starts the in-flight check
    isDocumentHidden = true;
    await act(async () => {
      rejectInFlight(new Error("app suspended"));
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(store.get(backendStatusAtom).status).toBe("running");
  });

  it("stays in the loading state when the backend has never responded", async () => {
    isBackendHealthy = false;
    const store = renderBoundary();
    await flushMicrotasks();
    await advanceOnePoll();

    expect(store.get(backendStatusAtom).status).toBe("loading");
  });
});
