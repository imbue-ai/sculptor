import { renderHook } from "@testing-library/react";
import type { WritableAtom } from "jotai";
import { Provider } from "jotai";
import { useHydrateAtoms } from "jotai/utils";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type * as api from "../../../api";
import type { CodingAgentTaskView } from "../../../api";
import { taskAtomFamily, taskIdsAtom } from "../atoms/tasks";
import type { TabsState } from "../atoms/workspaces";
import { INVALID_ACTIVE_INDEX } from "../atoms/workspaces";
import { useWorkspaceNavigation } from "./useWorkspaceNavigation";

const mockNavigateToAgent = vi.fn();
const mockNavigateToWorkspace = vi.fn();

// Mock the API call so openWorkspaceTabAtom's fire-and-forget PATCH doesn't
// throw "Failed to parse URL" in the test environment (no API base URL).
vi.mock("../../../api", async () => {
  const actual = await vi.importActual<typeof api>("../../../api");
  return {
    ...actual,
    updateWorkspace: vi.fn().mockResolvedValue({ data: {} }),
    batchUpdateOpenState: vi.fn().mockResolvedValue({ data: {} }),
  };
});

vi.mock("~/common/NavigateUtils.ts", () => ({
  useImbueNavigate: (): Record<string, unknown> => ({
    navigateToAgent: mockNavigateToAgent,
    navigateToWorkspace: mockNavigateToWorkspace,
    navigateToAddWorkspace: vi.fn(),
    navigateToHome: vi.fn(),
    navigateToGlobalSettings: vi.fn(),
    navigateToRoot: vi.fn(),
  }),
  useImbueLocation: (): Record<string, unknown> => ({
    isAgentRoute: false,
    isAddWorkspaceRoute: false,
    addWorkspaceDraftId: null,
    isHomeRoute: false,
    isSettingsRoute: false,
  }),
}));

// eslint-disable-next-line @typescript-eslint/no-explicit-any, @typescript-eslint/array-type
type AnyWritableAtom = WritableAtom<unknown, any[], any>;
type AtomInitialValues = Array<readonly [AnyWritableAtom, unknown]>;

const HydrateAtoms = ({
  initialValues,
  children,
}: {
  initialValues: AtomInitialValues;
  children: ReactNode;
}): ReactNode => {
  useHydrateAtoms(initialValues);
  return children;
};

const createWrapper = (initialValues: AtomInitialValues = []) => {
  return ({ children }: { children: ReactNode }): ReactNode => (
    <Provider>
      <HydrateAtoms initialValues={initialValues}>{children}</HydrateAtoms>
    </Provider>
  );
};

const createMockTask = (overrides: Partial<CodingAgentTaskView> = {}): CodingAgentTaskView =>
  ({
    id: "task-1",
    projectId: "proj-1",
    createdAt: "2024-01-01T00:00:00Z",
    updatedAt: "2024-01-01T00:00:00Z",
    taskStatus: "RUNNING",
    isAutoCompacting: false,
    artifactNames: [],
    initialPrompt: "Test prompt",
    titleOrSomethingLikeIt: "Test task",
    interface: "API",
    systemPrompt: null,
    model: "CLAUDE_4_SONNET",
    isSmoothStreamingSupported: true,
    isArchived: false,
    isDeleted: false,
    title: "Test task",
    status: "RUNNING",
    goal: "Test goal",
    workspaceId: null,
    ...overrides,
  }) as CodingAgentTaskView;

const seedTabsLocalStorage = (state: TabsState): void => {
  localStorage.setItem("sculptor-tabs", JSON.stringify(state));
};

describe("useWorkspaceNavigation", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.removeItem("sculptor-tabs");
    localStorage.removeItem("sculptor-tab-order");
  });

  it("navigates to the saved agent when tabsAtom has an entry for the workspace", () => {
    seedTabsLocalStorage({
      order: [{ tabId: "ws_1", agentId: "agent-mru" }],
      activeIndex: INVALID_ACTIVE_INDEX,
    });

    const { result } = renderHook(() => useWorkspaceNavigation(), {
      wrapper: createWrapper(),
    });

    result.current.handleWorkspaceClick({ objectId: "ws_1", isOpen: true } as never);

    expect(mockNavigateToAgent).toHaveBeenCalledWith("ws_1", "agent-mru");
    expect(mockNavigateToWorkspace).not.toHaveBeenCalled();
  });

  it("navigates to workspace URL (not first task) when no saved agent is recorded", () => {
    // Simulate fresh state: workspace tab has no saved agent yet, but tasks
    // exist. The first task is NOT the MRU agent.
    const task1 = createMockTask({ id: "agent-first", workspaceId: "ws_1" });
    const task2 = createMockTask({ id: "agent-mru", workspaceId: "ws_1" });
    seedTabsLocalStorage({
      order: [{ tabId: "ws_1", agentId: null }],
      activeIndex: INVALID_ACTIVE_INDEX,
    });

    const { result } = renderHook(() => useWorkspaceNavigation(), {
      wrapper: createWrapper([
        [taskIdsAtom, ["agent-first", "agent-mru"]],
        [taskAtomFamily("agent-first"), task1],
        [taskAtomFamily("agent-mru"), task2],
      ]),
    });

    result.current.handleWorkspaceClick({ objectId: "ws_1", isOpen: true } as never);

    // Should NOT navigate to the first task — that would pick the wrong agent.
    // Instead, should navigate to the workspace URL so WorkspacePage's
    // validation effect resolves the right agent.
    expect(mockNavigateToAgent).not.toHaveBeenCalled();
    expect(mockNavigateToWorkspace).toHaveBeenCalledWith("ws_1");
  });

  it("navigates to workspace URL when no entry exists in tabsAtom", () => {
    const { result } = renderHook(() => useWorkspaceNavigation(), {
      wrapper: createWrapper(),
    });

    result.current.handleWorkspaceClick({ objectId: "ws_1", isOpen: true } as never);

    expect(mockNavigateToAgent).not.toHaveBeenCalled();
    expect(mockNavigateToWorkspace).toHaveBeenCalledWith("ws_1");
  });
});
