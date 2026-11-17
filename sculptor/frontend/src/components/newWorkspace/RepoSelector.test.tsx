import { act, cleanup, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createStore } from "jotai";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { DependenciesStatus, DependencyInfo, Project } from "~/api";
import { ElementIds } from "~/api";
import { dependenciesStatusAtom } from "~/common/state/atoms/dependenciesStatus.ts";
import { renderWithProviders } from "~/common/utils/renderWithProviders.tsx";

import { RepoSelector } from "./RepoSelector.tsx";

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

// Opening the dropdown also warms the remote repo list; that fetch is not under test.
vi.mock("~/components/addRepo/hooks/useRemoteRepos.ts", async (importOriginal) => {
  const original = await importOriginal();
  return {
    ...(original as object),
    prefetchInitialRemoteRepos: vi.fn(),
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

const PROJECT = { objectId: "p1", name: "Repo One" } as Project;

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("RepoSelector", () => {
  it("asks the backend to re-check when the dropdown opens, and keeps a newer stream frame", async () => {
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
    renderWithProviders(<RepoSelector projects={[PROJECT]} selectedProjectId="p1" onProjectChange={vi.fn()} />, {
      store,
    });

    await userEvent.click(screen.getByTestId(ElementIds.PROJECT_SELECTOR));
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
