import { QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup } from "@testing-library/react";
import { createStore } from "jotai";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { DependenciesStatus, DependencyInfo } from "~/api";
import { dependenciesStatusAtom } from "~/common/state/atoms/dependenciesStatus.ts";
import { queryClient } from "~/common/state/queryClient.ts";
import { renderWithProviders } from "~/common/utils/renderWithProviders.tsx";

import { AddRepoDialog } from "./AddRepoDialog.tsx";

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

const makeInfo = (overrides: Partial<DependencyInfo>): DependencyInfo => ({ installed: false, ...overrides });

const makeStatus = (gh: DependencyInfo): DependenciesStatus => ({
  git: makeInfo({ installed: true }),
  claude: makeInfo({ installed: true }),
  pi: makeInfo({}),
  gh,
  jj: makeInfo({}),
  jjReadiness: { blocker: "NOT_INSTALLED" },
  voiceModels: makeInfo({}),
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("AddRepoDialog", () => {
  it("asks the backend to re-check on open, and keeps a newer stream frame when the response lands after it", async () => {
    const store = createStore();
    const ghMissing = makeStatus(makeInfo({ installed: false }));
    const ghReady = makeStatus(makeInfo({ installed: true, isAuthenticated: true }));
    store.set(dependenciesStatusAtom, ghMissing);
    let resolveRecheck: (status: DependenciesStatus) => void = () => {};
    mockGetDependenciesStatus.mockReturnValue(
      new Promise((resolve) => {
        resolveRecheck = (status): void => resolve({ data: status });
      }),
    );

    renderWithProviders(
      <QueryClientProvider client={queryClient}>
        <AddRepoDialog open onOpenChange={vi.fn()} setToast={vi.fn()} />
      </QueryClientProvider>,
      { store },
    );
    act(() => {
      store.set(dependenciesStatusAtom, ghReady);
    });
    await act(async () => {
      resolveRecheck(ghMissing);
    });

    expect(mockGetDependenciesStatus).toHaveBeenCalledWith({ meta: { skipWsAck: true } });
    expect(store.get(dependenciesStatusAtom)).toBe(ghReady);
  });
});
