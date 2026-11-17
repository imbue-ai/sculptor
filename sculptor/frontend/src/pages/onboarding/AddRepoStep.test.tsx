import { QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, screen } from "@testing-library/react";
import { createStore } from "jotai";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { DependenciesStatus, DependencyInfo } from "~/api";
import { ElementIds } from "~/api";
import { dependenciesStatusAtom } from "~/common/state/atoms/dependenciesStatus.ts";
import { queryClient } from "~/common/state/queryClient.ts";
import { renderWithProviders } from "~/common/utils/renderWithProviders.tsx";

import { AddRepoStep } from "./AddRepoStep.tsx";

const { mockGetDependenciesStatus, mockListRemoteRepos } = vi.hoisted(() => ({
  mockGetDependenciesStatus: vi.fn(),
  mockListRemoteRepos: vi.fn(),
}));

vi.mock("~/api", async (importOriginal) => {
  const original = await importOriginal();
  return {
    ...(original as object),
    getDependenciesStatus: mockGetDependenciesStatus,
    listRemoteRepos: mockListRemoteRepos,
  };
});

const makeInfo = (overrides: Partial<DependencyInfo>): DependencyInfo => ({ installed: false, ...overrides });

const GH_READY: DependenciesStatus = {
  git: makeInfo({ installed: true }),
  claude: makeInfo({ installed: true }),
  pi: makeInfo({}),
  gh: makeInfo({ installed: true, isAuthenticated: true }),
  jj: makeInfo({}),
  jjReadiness: { blocker: "NOT_INSTALLED" },
  voiceModels: makeInfo({}),
};

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  queryClient.clear();
});

describe("AddRepoStep", () => {
  it("renders the GitHub form from its own status fetch, leaving the shared store untouched", async () => {
    // Onboarding renders before the unified stream connects, so nothing else
    // delivers the status here.
    const store = createStore();
    mockGetDependenciesStatus.mockResolvedValue({ data: GH_READY });
    mockListRemoteRepos.mockResolvedValue({ data: [] });

    renderWithProviders(
      <QueryClientProvider client={queryClient}>
        <AddRepoStep onComplete={vi.fn().mockResolvedValue(undefined)} isLoading={false} error={null} />
      </QueryClientProvider>,
      { store },
    );
    await act(async () => {});
    fireEvent.click(screen.getByTestId(ElementIds.ADD_REPO_SOURCE_GITHUB));

    expect(mockGetDependenciesStatus).toHaveBeenCalledWith({ meta: { skipWsAck: true } });
    expect(screen.queryByTestId(ElementIds.ADD_REPO_NOT_CONFIGURED)).not.toBeInTheDocument();
    expect(store.get(dependenciesStatusAtom)).toBeNull();
  });
});
