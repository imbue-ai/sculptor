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

  it("re-checks availability on mount so a pi installed mid-session is picked up", async () => {
    // The stream's last push predates the binary: pi reads unavailable.
    store.set(dependenciesStatusAtom, makeStatus({}));
    mockGetDependenciesStatus.mockResolvedValue({ data: PI_AVAILABLE_STATUS });

    const { result } = renderHook(() => usePiAgentOption(), { wrapper });

    expect(result.current.isPiAvailable).toBe(false);
    await waitFor(() => {
      expect(result.current.isPiAvailable).toBe(true);
    });
    expect(mockGetDependenciesStatus).toHaveBeenCalledWith({ meta: { skipWsAck: true } });
  });

  it("re-checks availability when a picker asks (e.g. on its dropdown opening)", async () => {
    // The hook's consumer mounted before the binary appeared (e.g. the
    // first-run dialog), so the mount re-check saw pi unavailable.
    store.set(dependenciesStatusAtom, makeStatus({}));
    mockGetDependenciesStatus.mockResolvedValue({ data: makeStatus({}) });

    const { result } = renderHook(() => usePiAgentOption(), { wrapper });

    await waitFor(() => {
      expect(mockGetDependenciesStatus).toHaveBeenCalledTimes(1);
    });
    expect(result.current.isPiAvailable).toBe(false);

    // pi lands on PATH afterwards; the picker's open-time refresh observes it.
    mockGetDependenciesStatus.mockResolvedValue({ data: PI_AVAILABLE_STATUS });
    act(() => {
      result.current.refreshPiAvailability();
    });

    await waitFor(() => {
      expect(result.current.isPiAvailable).toBe(true);
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
