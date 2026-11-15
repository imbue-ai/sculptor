import { act, renderHook } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { DependenciesStatus, DependencyInfo } from "~/api";
import { useVoiceModelsInstall } from "~/common/hooks/useVoiceEntry";
import { dependenciesStatusAtom } from "~/common/state/atoms/dependenciesStatus";

const { mockInstallDependency, mockGetDependenciesStatus } = vi.hoisted(() => ({
  mockInstallDependency: vi.fn(),
  mockGetDependenciesStatus: vi.fn(),
}));

vi.mock("~/api", async (importOriginal) => {
  const original = await importOriginal();
  return {
    ...(original as object),
    installDependency: mockInstallDependency,
    getDependenciesStatus: mockGetDependenciesStatus,
  };
});

// The poll loop has its own tests (usePollingInterval.test.ts); stub it so these
// tests stay timer-free. A test runs one poll tick by calling the function
// handed to startPolling.
const { mockStartPolling, mockStopPolling } = vi.hoisted(() => ({
  mockStartPolling: vi.fn(),
  mockStopPolling: vi.fn(),
}));
vi.mock("~/common/hooks/usePollingInterval", () => ({
  usePollingInterval: (): { startPolling: () => void; stopPolling: () => void } => ({
    startPolling: mockStartPolling,
    stopPolling: mockStopPolling,
  }),
}));

const makeInfo = (overrides: Partial<DependencyInfo>): DependencyInfo => ({ installed: false, ...overrides });

const makeStatus = (voiceModels: DependencyInfo): DependenciesStatus => ({
  git: makeInfo({ installed: true }),
  claude: makeInfo({ installed: true }),
  pi: makeInfo({}),
  gh: makeInfo({}),
  jj: makeInfo({}),
  jjReadiness: { blocker: "NOT_INSTALLED" },
  voiceModels,
});

const INSTALLING = makeStatus(
  makeInfo({ installProgress: { tool: "VOICE_MODELS", bytesDownloaded: 1, totalBytes: 10 } }),
);
const INSTALLED = makeStatus(makeInfo({ installed: true }));

describe("useVoiceModelsInstall", () => {
  let store: ReturnType<typeof createStore>;

  const wrapper = ({ children }: { children: ReactNode }): ReactElement => (
    <Provider store={store}>{children}</Provider>
  );

  const startInstall = async (): Promise<{ current: ReturnType<typeof useVoiceModelsInstall> }> => {
    store.set(dependenciesStatusAtom, INSTALLING);
    mockInstallDependency.mockResolvedValue({ data: { success: true } });
    const { result } = renderHook(() => useVoiceModelsInstall(), { wrapper });
    await act(async () => {
      result.current.handleInstall();
    });
    return result;
  };

  beforeEach(() => {
    store = createStore();
    vi.clearAllMocks();
  });

  it("keeps a newer stream frame when a poll response lands after it", async () => {
    await startInstall();
    let resolvePoll: (status: DependenciesStatus) => void = () => {};
    mockGetDependenciesStatus.mockReturnValue(
      new Promise((resolve) => {
        resolvePoll = (status): void => resolve({ data: status });
      }),
    );

    const pollFn = mockStartPolling.mock.lastCall?.[0] as () => Promise<void>;
    let tick: Promise<void> = Promise.resolve();
    act(() => {
      tick = pollFn();
    });
    act(() => {
      store.set(dependenciesStatusAtom, INSTALLED);
    });
    await act(async () => {
      resolvePoll(INSTALLING);
      await tick;
    });

    expect(store.get(dependenciesStatusAtom)).toBe(INSTALLED);
  });

  it("stops once a poll response reports the install finished, leaving the status to the stream", async () => {
    await startInstall();
    mockGetDependenciesStatus.mockResolvedValue({ data: INSTALLED });

    const pollFn = mockStartPolling.mock.lastCall?.[0] as () => Promise<void>;
    await act(async () => {
      await pollFn();
    });

    expect(mockStopPolling).toHaveBeenCalled();
    expect(store.get(dependenciesStatusAtom)).toBe(INSTALLING);
  });
});
