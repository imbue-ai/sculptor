import { act, renderHook, waitFor } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { DependenciesStatus, DependencyInfo } from "~/api";
import { dependenciesStatusAtom } from "~/common/state/atoms/dependenciesStatus";
import { usePiAgentOption } from "~/common/state/hooks/usePiAgentOption";

const { mockGetDependenciesStatus } = vi.hoisted(() => ({
  mockGetDependenciesStatus: vi.fn(),
}));

vi.mock("~/api", async (importOriginal) => {
  const original = await importOriginal();
  return {
    ...(original as object),
    getDependenciesStatus: mockGetDependenciesStatus,
  };
});

// Routing is exercised by the pickers' integration tests; this file asserts only
// the availability state, so the settings navigation is stubbed out.
vi.mock("~/common/state/hooks/useOpenSettings", () => ({
  useOpenSettings: (): ((section?: string) => void) => vi.fn(),
}));

const makeInfo = (overrides: Partial<DependencyInfo>): DependencyInfo => ({ installed: false, ...overrides });

const makeStatus = (overrides: Partial<DependenciesStatus>): DependenciesStatus => ({
  git: makeInfo({ installed: true }),
  claude: makeInfo({}),
  pi: makeInfo({}),
  gh: makeInfo({}),
  jj: makeInfo({}),
  jjReadiness: { blocker: "NOT_INSTALLED" },
  voiceModels: makeInfo({}),
  ...overrides,
});

const PI_AVAILABLE_STATUS = makeStatus({ pi: makeInfo({ installed: true, isVersionInRange: true }) });

describe("usePiAgentOption", () => {
  let store: ReturnType<typeof createStore>;

  const wrapper = ({ children }: { children: ReactNode }): ReactElement => (
    <Provider store={store}>{children}</Provider>
  );

  beforeEach(() => {
    store = createStore();
    vi.clearAllMocks();
  });

  it("asks the backend to re-check on mount, and leaves the status to the stream", async () => {
    // The stream's last push predates the binary: pi reads unavailable.
    store.set(dependenciesStatusAtom, makeStatus({}));
    mockGetDependenciesStatus.mockResolvedValue({ data: PI_AVAILABLE_STATUS });

    const { result } = renderHook(() => usePiAgentOption(), { wrapper });
    await act(async () => {});

    expect(mockGetDependenciesStatus).toHaveBeenCalledWith({ meta: { skipWsAck: true } });
    expect(result.current.isPiAvailable).toBe(false);

    // The backend publishes the re-checked status on the stream.
    act(() => {
      store.set(dependenciesStatusAtom, PI_AVAILABLE_STATUS);
    });
    expect(result.current.isPiAvailable).toBe(true);
  });

  it("keeps a newer stream frame when the re-check response lands after it", async () => {
    store.set(dependenciesStatusAtom, makeStatus({}));
    let resolveRecheck: (status: DependenciesStatus) => void = () => {};
    mockGetDependenciesStatus.mockReturnValue(
      new Promise((resolve) => {
        resolveRecheck = (status): void => resolve({ data: status });
      }),
    );

    const { result } = renderHook(() => usePiAgentOption(), { wrapper });
    act(() => {
      store.set(dependenciesStatusAtom, PI_AVAILABLE_STATUS);
    });
    await act(async () => {
      resolveRecheck(makeStatus({}));
    });

    expect(store.get(dependenciesStatusAtom)).toBe(PI_AVAILABLE_STATUS);
    expect(result.current.isPiAvailable).toBe(true);
  });

  it("re-checks availability when a picker asks (e.g. on its dropdown opening)", async () => {
    store.set(dependenciesStatusAtom, makeStatus({}));
    mockGetDependenciesStatus.mockResolvedValue({ data: makeStatus({}) });

    const { result } = renderHook(() => usePiAgentOption(), { wrapper });

    await waitFor(() => {
      expect(mockGetDependenciesStatus).toHaveBeenCalledTimes(1);
    });
    act(() => {
      result.current.refreshPiAvailability();
    });

    await waitFor(() => {
      expect(mockGetDependenciesStatus).toHaveBeenCalledTimes(2);
    });
  });

  it("keeps the last known status when the availability re-check fails", async () => {
    store.set(dependenciesStatusAtom, PI_AVAILABLE_STATUS);
    mockGetDependenciesStatus.mockRejectedValue(new Error("backend unreachable"));

    const { result } = renderHook(() => usePiAgentOption(), { wrapper });

    await waitFor(() => {
      expect(mockGetDependenciesStatus).toHaveBeenCalled();
    });
    expect(result.current.isPiAvailable).toBe(true);
    expect(store.get(dependenciesStatusAtom)).toBe(PI_AVAILABLE_STATUS);
  });
});
