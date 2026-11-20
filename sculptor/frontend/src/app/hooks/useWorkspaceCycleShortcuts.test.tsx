import { renderHook } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type * as api from "~/api";
import type { TabsState } from "~/common/state/atoms/workspaces.ts";
import { INVALID_ACTIVE_INDEX, SCULPTOR_TABS_STORAGE_KEY, tabsAtom } from "~/common/state/atoms/workspaces.ts";
import { commandActionsAtom } from "~/components/commandPalette/utils/commandActions.ts";

import { useWorkspaceCycleShortcuts } from "./useWorkspaceCycleShortcuts.ts";

const mockNavigateToAgent = vi.fn();
const mockNavigateToWorkspace = vi.fn();

vi.mock("~/common/hooks/navigation.ts", () => ({
  useImbueNavigate: (): Record<string, unknown> => ({
    navigateToAgent: mockNavigateToAgent,
    navigateToWorkspace: mockNavigateToWorkspace,
  }),
}));

// A custom sidebar order: B above A above C.
vi.mock("~/app/nav/sidebarWorkspaceOrder.ts", async () => {
  const { atom } = await import("jotai");
  return {
    sidebarOrderedWorkspacesAtom: atom([{ objectId: "ws_b" }, { objectId: "ws_a" }, { objectId: "ws_c" }]),
  };
});

// openWorkspaceTabAtom fires a PATCH that has no API base URL in tests.
vi.mock("~/api", async () => {
  const actual = await vi.importActual<typeof api>("~/api");
  return {
    ...actual,
    updateWorkspace: vi.fn().mockResolvedValue({ data: {} }),
    batchUpdateOpenState: vi.fn().mockResolvedValue({ data: {} }),
  };
});

// The hook reads saved agents from the store at press time, so seed the store
// itself: tabsAtom reads localStorage only when it is created or subscribed.
const pressNextWorkspace = (savedAgents: TabsState["order"]): void => {
  const store = createStore();
  store.set(tabsAtom, { order: savedAgents, activeIndex: INVALID_ACTIVE_INDEX });
  renderHook(() => useWorkspaceCycleShortcuts(), {
    wrapper: ({ children }: { children: ReactNode }): ReactNode => <Provider store={store}>{children}</Provider>,
  });
  store.get(commandActionsAtom)["workspace.nextTab"]?.();
};

describe("useWorkspaceCycleShortcuts", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.removeItem(SCULPTOR_TABS_STORAGE_KEY);
    window.location.hash = "#/ws/ws_b/agent/agent-b";
  });

  it("goes straight to the next workspace's saved agent, in sidebar order", () => {
    pressNextWorkspace([
      { tabId: "ws_a", agentId: "agent-a" },
      { tabId: "ws_b", agentId: "agent-b" },
      { tabId: "ws_c", agentId: "agent-c" },
    ]);

    expect(mockNavigateToAgent).toHaveBeenCalledWith("ws_a", "agent-a");
    expect(mockNavigateToWorkspace).not.toHaveBeenCalled();
  });

  it("opens the workspace itself when the next workspace has no saved agent", () => {
    pressNextWorkspace([{ tabId: "ws_b", agentId: "agent-b" }]);

    expect(mockNavigateToWorkspace).toHaveBeenCalledWith("ws_a");
    expect(mockNavigateToAgent).not.toHaveBeenCalled();
  });
});
