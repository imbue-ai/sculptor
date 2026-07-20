import { act, renderHook } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { DependenciesStatus, DependencyInfo } from "~/api";
import { UserConfigField } from "~/api";
import { dependenciesStatusAtom } from "~/common/state/atoms/dependenciesStatus";
import { useManagedDependency } from "~/common/useManagedDependency";

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
// tests stay timer-free and assert only the hook's own state handling.
vi.mock("~/common/usePollingInterval", () => ({
  usePollingInterval: (): { startPolling: () => void; stopPolling: () => void } => ({
    startPolling: vi.fn(),
    stopPolling: vi.fn(),
  }),
}));

const makeInfo = (overrides: Partial<DependencyInfo>): DependencyInfo => ({ installed: false, ...overrides });

const makeStatus = (overrides: Partial<DependenciesStatus>): DependenciesStatus => ({
  git: makeInfo({ installed: true }),
  claude: makeInfo({}),
  pi: makeInfo({}),
  gh: makeInfo({}),
  ...overrides,
});

describe("useManagedDependency", () => {
  let store: ReturnType<typeof createStore>;
  const onSettingChange = vi.fn().mockResolvedValue(undefined);

  const wrapper = ({ children }: { children: ReactNode }): ReactElement => (
    <Provider store={store}>{children}</Provider>
  );

  beforeEach(() => {
    store = createStore();
    vi.clearAllMocks();
    mockGetDependenciesStatus.mockResolvedValue({ data: makeStatus({}) });
  });

  it("treats an installed, in-range managed binary as up to date and suppresses a stale error", () => {
    store.set(
      dependenciesStatusAtom,
      makeStatus({
        pi: makeInfo({
          installed: true,
          version: "0.80.10",
          mode: "MANAGED",
          source: "MANAGED",
          isVersionInRange: true,
          installError: "stale error from an earlier attempt",
        }),
      }),
    );

    const { result } = renderHook(() => useManagedDependency({ tool: "PI", onSettingChange }), { wrapper });

    expect(result.current.mode).toBe("MANAGED");
    expect(result.current.displayMode).toBe("MANAGED");
    expect(result.current.isManagedUpToDate).toBe(true);
    expect(result.current.effectiveInstallError).toBeNull();
  });

  it("does not treat a PATH-fallback pi as a managed install being up to date", () => {
    // pi's MANAGED mode resolves a system-PATH binary while no managed copy is
    // downloaded; that binary being healthy must not read as "managed install
    // up to date", nor suppress a managed-install error.
    store.set(
      dependenciesStatusAtom,
      makeStatus({
        pi: makeInfo({
          installed: true,
          version: "0.80.10",
          mode: "MANAGED",
          source: "EXTERNAL",
          isVersionInRange: true,
          installError: "managed download failed",
        }),
      }),
    );

    const { result } = renderHook(() => useManagedDependency({ tool: "PI", onSettingChange }), { wrapper });

    expect(result.current.isManagedUpToDate).toBe(false);
    expect(result.current.effectiveInstallError).toBe("managed download failed");
  });

  it("surfaces the backend install error while the binary is not up to date", () => {
    store.set(
      dependenciesStatusAtom,
      makeStatus({
        claude: makeInfo({
          installed: false,
          mode: "MANAGED",
          isVersionInRange: false,
          installError: "download failed",
        }),
      }),
    );

    const { result } = renderHook(() => useManagedDependency({ tool: "CLAUDE", onSettingChange }), { wrapper });

    expect(result.current.isManagedUpToDate).toBe(false);
    expect(result.current.effectiveInstallError).toBe("download failed");
  });

  it("computes the download progress percent from the install progress bytes", () => {
    store.set(
      dependenciesStatusAtom,
      makeStatus({
        pi: makeInfo({
          installed: false,
          mode: "MANAGED",
          installProgress: { tool: "PI", bytesDownloaded: 50, totalBytes: 200 },
        }),
      }),
    );

    const { result } = renderHook(() => useManagedDependency({ tool: "PI", onSettingChange }), { wrapper });

    expect(result.current.progressPercent).toBe(25);
  });

  it("handleModeChange optimistically switches displayMode and persists the per-tool field", () => {
    store.set(
      dependenciesStatusAtom,
      makeStatus({ pi: makeInfo({ installed: true, mode: "MANAGED", isVersionInRange: true }) }),
    );

    const { result } = renderHook(() => useManagedDependency({ tool: "PI", onSettingChange }), { wrapper });

    act(() => {
      result.current.handleModeChange("CUSTOM");
    });

    expect(result.current.displayMode).toBe("CUSTOM");
    expect(result.current.isModeSettling).toBe(true);
    expect(onSettingChange).toHaveBeenCalledWith(UserConfigField.DEPENDENCY_PATHS, { pi: "CUSTOM" });
  });

  it("handleInstall requests the install for the given tool and reports an immediate failure", async () => {
    store.set(
      dependenciesStatusAtom,
      makeStatus({ claude: makeInfo({ installed: false, mode: "MANAGED", isVersionInRange: false }) }),
    );
    mockInstallDependency.mockResolvedValue({ data: { success: false, error: "no network" } });

    const { result } = renderHook(() => useManagedDependency({ tool: "CLAUDE", onSettingChange }), { wrapper });

    await act(async () => {
      await result.current.handleInstall();
    });

    // The install endpoint opens no request transaction, so it never acks on the
    // unified stream; skipWsAck avoids a spurious 10s timeout while the background
    // install (polled below) is still running.
    expect(mockInstallDependency).toHaveBeenCalledWith({ query: { tool: "CLAUDE" }, meta: { skipWsAck: true } });
    expect(result.current.isInstalling).toBe(false);
    expect(result.current.effectiveInstallError).toBe("no network");
  });
});
