import { act, cleanup, renderHook } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type * as ApiModule from "~/api";
import {
  createWorkspaceAgent,
  createWorkspaceV2,
  getCurrentBranch,
  previewBranchName,
  WorkspaceInitializationStrategy,
} from "~/api";
import type * as NavigationModule from "~/common/hooks/navigation.ts";

import { lastWorkspaceCreationSettingsAtom, newWorkspaceDialogAtom } from "./newWorkspaceAtoms.ts";
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

const { IN_PLACE, CLONE, WORKTREE } = WorkspaceInitializationStrategy;

const renderSidebarCreate = (
  initStrategy: WorkspaceInitializationStrategy,
): { store: ReturnType<typeof createStore>; createFromSidebar: (projectId: string) => Promise<void> } => {
  const store = createStore();
  store.set(lastWorkspaceCreationSettingsAtom, { projectId: "p1", agentType: "claude", initStrategy });
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
    const { store, createFromSidebar } = renderSidebarCreate(CLONE);

    await createFromSidebarFor(createFromSidebar);

    const body = getWorkspaceRequestBody();
    expect(body.initializationStrategy).toBe(CLONE);
    expect(body.requestedBranchName).toBe("dev/fresh-slug");
    expect(body.sourceBranch).toBeUndefined();
    expect(store.get(newWorkspaceDialogAtom).open).toBe(false);
  });

  it("opens the dialog for a worktree when the current-branch lookup fails", async () => {
    vi.mocked(getCurrentBranch).mockRejectedValue(new Error("offline"));
    const { store, createFromSidebar } = renderSidebarCreate(WORKTREE);

    await createFromSidebarFor(createFromSidebar);

    expect(createWorkspaceV2).not.toHaveBeenCalled();
    expect(store.get(newWorkspaceDialogAtom)).toEqual({ open: true, presetProjectId: "p1" });
  });

  it("creates an in-place workspace without looking up any branch", async () => {
    const { createFromSidebar } = renderSidebarCreate(IN_PLACE);

    await createFromSidebarFor(createFromSidebar);

    expect(getCurrentBranch).not.toHaveBeenCalled();
    expect(previewBranchName).not.toHaveBeenCalled();
    const body = getWorkspaceRequestBody();
    expect(body.initializationStrategy).toBe(IN_PLACE);
    expect(body.requestedBranchName).toBeUndefined();
    expect(body.sourceBranch).toBeUndefined();
  });
});
