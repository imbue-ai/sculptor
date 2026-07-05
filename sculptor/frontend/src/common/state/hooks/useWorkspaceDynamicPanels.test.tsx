import { act, renderHook } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import type { CodingAgentTaskView } from "~/api";
import { agentAtomFamily, agentIdsAtom } from "~/common/state/atoms/agents.ts";
import { agentDeleteTargetAtom } from "~/components/commandPalette/contextActions/atoms/contextActions.ts";
import { makeAgentPanelId } from "~/pages/workspace/layout/registry/dynamicPanels.tsx";
import { panelRegistryAtom } from "~/pages/workspace/layout/registry/panelRegistry.ts";

import { useWorkspaceDynamicPanels } from "./useWorkspaceDynamicPanels.ts";

// Diagnostics are fetched lazily over the API; the registry wiring under test
// does not need them.
vi.mock("./useWorkspaceAgentDiagnostics.ts", () => ({
  useWorkspaceAgentDiagnostics: (): Record<string, never> => ({}),
}));

const WORKSPACE_ID = "ws-1";

const createMockAgent = (overrides: Partial<CodingAgentTaskView> = {}): CodingAgentTaskView =>
  ({
    id: "agent-1",
    projectId: "proj-1",
    createdAt: "2024-01-01T00:00:00Z",
    updatedAt: "2024-01-01T00:00:00Z",
    agentStatus: "RUNNING",
    isAutoCompacting: false,
    artifactNames: [],
    initialPrompt: "Test prompt",
    titleOrSomethingLikeIt: "Claude 2",
    interface: "API",
    systemPrompt: null,
    model: "CLAUDE_4_SONNET",
    harnessCapabilities: {},
    isSmoothStreamingSupported: true,
    isArchived: false,
    isDeleted: false,
    title: null,
    status: "RUNNING",
    goal: "Test goal",
    lastReadAt: null,
    workspaceId: WORKSPACE_ID,
    ...overrides,
  }) as CodingAgentTaskView;

const renderWithAgent = (agent: CodingAgentTaskView): ReturnType<typeof createStore> => {
  const store = createStore();
  store.set(agentIdsAtom, [agent.id]);
  store.set(agentAtomFamily(agent.id), agent);

  const wrapper = ({ children }: { children: ReactNode }): ReactElement => (
    <Provider store={store}>{children}</Provider>
  );
  renderHook(() => useWorkspaceDynamicPanels(WORKSPACE_ID), { wrapper });
  return store;
};

describe("useWorkspaceDynamicPanels agent close target", () => {
  it("falls back to the tab display name for an untitled agent's delete confirmation", () => {
    const store = renderWithAgent(createMockAgent({ title: null, titleOrSomethingLikeIt: "Claude 2" }));

    const agentPanel = store.get(panelRegistryAtom).find((panel) => panel.id === makeAgentPanelId("agent-1"));
    expect(agentPanel).toBeDefined();

    act(() => agentPanel?.onRequestClose?.());
    expect(store.get(agentDeleteTargetAtom)).toEqual({ id: "agent-1", name: "Claude 2" });
  });

  it("uses the explicit title when the agent has one", () => {
    const store = renderWithAgent(createMockAgent({ title: "My agent" }));

    const agentPanel = store.get(panelRegistryAtom).find((panel) => panel.id === makeAgentPanelId("agent-1"));
    act(() => agentPanel?.onRequestClose?.());
    expect(store.get(agentDeleteTargetAtom)).toEqual({ id: "agent-1", name: "My agent" });
  });
});
