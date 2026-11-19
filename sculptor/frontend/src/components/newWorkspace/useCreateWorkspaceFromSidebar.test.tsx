import { act, cleanup, renderHook } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type * as ApiModule from "~/api";
import type { DependenciesStatus, Project } from "~/api";
import {
  createWorkspaceAgent,
  createWorkspaceV2,
  getCurrentBranch,
  previewBranchName,
  WorkspaceInitializationStrategy,
} from "~/api";
import type * as NavigationModule from "~/common/hooks/navigation.ts";
import { dependenciesStatusAtom } from "~/common/state/atoms/dependenciesStatus.ts";
import { projectJjStateAtomFamily } from "~/common/state/atoms/projectJjState.ts";
import { updateProjectsAtom } from "~/common/state/atoms/projects.ts";

import {
  lastCreationSettingsByProjectIdAtom,
  lastWorkspaceCreationSettingsAtom,
  newWorkspaceDialogAtom,
} from "./newWorkspaceAtoms.ts";
import { useCreateWorkspaceFromSidebar } from "./useCreateWorkspaceFromSidebar.ts";

// The quick create looks branches up over the API and creates through
// useCreateWorkspace, so the API, the router, the registrations query and
// analytics are stubbed at their module seams.
vi.mock("~/api", async (importOriginal) => ({
  ...(await importOriginal<typeof ApiModule>()),
  getCurrentBranch: vi.fn(),
  previewBranchName: vi.fn(),
  createWorkspaceV2: vi.fn(),
  createWorkspaceAgent: vi.fn(),
}));

vi.mock("~/common/hooks/navigation.ts", async (importOriginal) => ({
  ...(await importOriginal<typeof NavigationModule>()),
  useImbueNavigate: (): Record<string, unknown> => ({ navigateToWorkspace: vi.fn(), navigateToAgent: vi.fn() }),
}));

vi.mock("~/common/state/hooks/useTerminalAgentRegistrations.ts", () => ({
  useTerminalAgentRegistrations: (): unknown => ({ registrations: [], refetch: vi.fn() }),
}));

vi.mock("posthog-js", () => ({ posthog: { capture: vi.fn() } }));

const { IN_PLACE, CLONE, WORKTREE, JJ_WORKSPACE } = WorkspaceInitializationStrategy;

const renderSidebarCreate = (
  byProjectId: Readonly<Record<string, { mode: WorkspaceInitializationStrategy; sourceBranch?: string }>>,
  prepareStore: (store: ReturnType<typeof createStore>) => void = (): void => {},
): { store: ReturnType<typeof createStore>; createFromSidebar: (projectId: string) => Promise<void> } => {
  const store = createStore();
  prepareStore(store);
  store.set(lastWorkspaceCreationSettingsAtom, { projectId: "p1", agentType: "claude" });
  store.set(lastCreationSettingsByProjectIdAtom, byProjectId);
  const wrapper = ({ children }: { children: ReactNode }): ReactElement => (
    <Provider store={store}>{children}</Provider>
  );
  const { result } = renderHook(() => useCreateWorkspaceFromSidebar(), { wrapper });
  return { store, createFromSidebar: result.current.createFromSidebar };
};

const createFromSidebarFor = async (createFromSidebar: (projectId: string) => Promise<void>): Promise<void> => {
  await act(async () => {
    await createFromSidebar("p1");
  });
};

const getWorkspaceRequestBody = (): Record<string, unknown> =>
  vi.mocked(createWorkspaceV2).mock.calls[0][0].body as unknown as Record<string, unknown>;

describe("useCreateWorkspaceFromSidebar", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getCurrentBranch).mockResolvedValue({
      data: { currentBranch: "main" },
    } as unknown as Awaited<ReturnType<typeof getCurrentBranch>>);
    vi.mocked(previewBranchName).mockResolvedValue({
      data: { branchName: "dev/fresh-slug" },
    } as unknown as Awaited<ReturnType<typeof previewBranchName>>);
    vi.mocked(createWorkspaceV2).mockResolvedValue({
      data: { objectId: "ws_1" },
    } as unknown as Awaited<ReturnType<typeof createWorkspaceV2>>);
    vi.mocked(createWorkspaceAgent).mockResolvedValue({
      data: { id: "agent_1" },
    } as unknown as Awaited<ReturnType<typeof createWorkspaceAgent>>);
  });

  // lastWorkspaceCreationSettingsAtom persists to localStorage, so wipe it too.
  afterEach(() => {
    cleanup();
    window.localStorage.clear();
  });

  it("still rolls a fresh branch name for a clone when the current-branch lookup fails", async () => {
    vi.mocked(getCurrentBranch).mockRejectedValue(new Error("offline"));
    const { store, createFromSidebar } = renderSidebarCreate({ p1: { mode: CLONE } });

    await createFromSidebarFor(createFromSidebar);

    const body = getWorkspaceRequestBody();
    expect(body.initializationStrategy).toBe(CLONE);
    expect(body.requestedBranchName).toBe("dev/fresh-slug");
    expect(body.sourceBranch).toBeUndefined();
    expect(store.get(newWorkspaceDialogAtom).open).toBe(false);
  });

  it("opens the dialog for a worktree when the current-branch lookup fails", async () => {
    vi.mocked(getCurrentBranch).mockRejectedValue(new Error("offline"));
    const { store, createFromSidebar } = renderSidebarCreate({ p1: { mode: WORKTREE } });

    await createFromSidebarFor(createFromSidebar);

    expect(createWorkspaceV2).not.toHaveBeenCalled();
    expect(store.get(newWorkspaceDialogAtom)).toEqual({ open: true, presetProjectId: "p1" });
  });

  it("uses the clicked repository's own last mode and source, not another repository's", async () => {
    const { createFromSidebar } = renderSidebarCreate({
      p1: { mode: CLONE, sourceBranch: "release" },
      p2: { mode: IN_PLACE },
    });

    await createFromSidebarFor(createFromSidebar);

    const body = getWorkspaceRequestBody();
    expect(body.initializationStrategy).toBe(CLONE);
    expect(body.sourceBranch).toBe("release");
    expect(getCurrentBranch).not.toHaveBeenCalled();
  });

  it("creates a worktree from the current branch in a git repository last used for a jj workspace", async () => {
    const { createFromSidebar } = renderSidebarCreate({ p1: { mode: JJ_WORKSPACE, sourceBranch: "main@origin" } });

    await createFromSidebarFor(createFromSidebar);

    const body = getWorkspaceRequestBody();
    expect(body.initializationStrategy).toBe(WORKTREE);
    expect(body.sourceBranch).toBe("main");
  });

  describe("in a repository that uses jj for new workspaces", () => {
    const useJjRepository =
      (isJjAvailable: boolean) =>
      (store: ReturnType<typeof createStore>): void => {
        store.set(updateProjectsAtom, [{ objectId: "p1", name: "Repo One", useJjForNewWorkspaces: true } as Project]);
        store.set(projectJjStateAtomFamily("p1"), {
          projectId: "p1",
          colocation: isJjAvailable ? "COLOCATED" : "ABSENT",
          colocationError: null,
          createsJjWorkspaces: isJjAvailable,
        });
        store.set(dependenciesStatusAtom, {
          pi: { installed: false },
          jjReadiness: isJjAvailable
            ? { blocker: null, identity: { name: "Dev", email: "dev@example.com" } }
            : { blocker: "NOT_INSTALLED" },
        } as DependenciesStatus);
      };

    it("creates a jj workspace that starts from its target, with a fresh bookmark name", async () => {
      const { createFromSidebar } = renderSidebarCreate({}, useJjRepository(true));

      await createFromSidebarFor(createFromSidebar);

      expect(getCurrentBranch).not.toHaveBeenCalled();
      expect(vi.mocked(previewBranchName).mock.calls[0][0].query).toEqual(
        expect.objectContaining({ project_id: "p1", mode: JJ_WORKSPACE }),
      );
      const body = getWorkspaceRequestBody();
      expect(body.initializationStrategy).toBe(JJ_WORKSPACE);
      expect(body.requestedBranchName).toBe("dev/fresh-slug");
      expect(body.sourceBranch).toBeUndefined();
    });

    it("replaces a worktree remembered for the repository with a jj workspace", async () => {
      const { createFromSidebar } = renderSidebarCreate(
        { p1: { mode: WORKTREE, sourceBranch: "main" } },
        useJjRepository(true),
      );

      await createFromSidebarFor(createFromSidebar);

      const body = getWorkspaceRequestBody();
      expect(body.initializationStrategy).toBe(JJ_WORKSPACE);
      expect(body.sourceBranch).toBeUndefined();
    });

    it("opens the dialog instead of creating while it is not yet known whether jj is available", async () => {
      const { store, createFromSidebar } = renderSidebarCreate({}, (preparedStore) => {
        useJjRepository(false)(preparedStore);
        preparedStore.set(dependenciesStatusAtom, null);
      });

      await createFromSidebarFor(createFromSidebar);

      expect(createWorkspaceV2).not.toHaveBeenCalled();
      expect(store.get(newWorkspaceDialogAtom)).toEqual({ open: true, presetProjectId: "p1" });
    });

    it("opens the dialog, which says why, instead of creating while jj is unavailable", async () => {
      const { store, createFromSidebar } = renderSidebarCreate({}, useJjRepository(false));

      await createFromSidebarFor(createFromSidebar);

      expect(createWorkspaceV2).not.toHaveBeenCalled();
      expect(store.get(newWorkspaceDialogAtom)).toEqual({ open: true, presetProjectId: "p1" });
    });
  });

  it("creates an in-place workspace without looking up any branch", async () => {
    const { createFromSidebar } = renderSidebarCreate({ p1: { mode: IN_PLACE } });

    await createFromSidebarFor(createFromSidebar);

    expect(getCurrentBranch).not.toHaveBeenCalled();
    expect(previewBranchName).not.toHaveBeenCalled();
    const body = getWorkspaceRequestBody();
    expect(body.initializationStrategy).toBe(IN_PLACE);
    expect(body.requestedBranchName).toBeUndefined();
    expect(body.sourceBranch).toBeUndefined();
  });
});
