import { cleanup, fireEvent, screen } from "@testing-library/react";
import { createStore } from "jotai";
import { afterEach, describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "~/common/testUtils.tsx";
import { agentDeleteTargetAtom } from "~/components/CommandPalette/contextActions/atoms.ts";
import { EMPTY_WORKSPACE_LAYOUT } from "~/components/sections/persistence/types.ts";
import { makeAgentPanelId } from "~/components/sections/registry/dynamicPanels.tsx";
import { activeWorkspaceIdAtom, workspaceLayoutAtom } from "~/components/sections/sectionAtoms.ts";

import { AgentDeleteConfirmation } from "./AgentDeleteConfirmation.tsx";

// The delete side effects (backend call, optimistic task removal, route navigation) are
// exercised elsewhere; here we only assert that confirming reconciles the section layout.
vi.mock("~/common/state/hooks/useOptimisticTaskDelete.ts", () => ({
  useOptimisticTaskDelete: (): { execute: () => void } => ({ execute: vi.fn() }),
}));

afterEach(cleanup);

describe("AgentDeleteConfirmation layout reconciliation", () => {
  it("reassigns a section's active tab to a sibling when the active-in-section agent is deleted", () => {
    const panelA = makeAgentPanelId("task-a");
    const panelB = makeAgentPanelId("task-b");
    const store = createStore();
    store.set(activeWorkspaceIdAtom, "ws-test");
    store.set(workspaceLayoutAtom, {
      ...EMPTY_WORKSPACE_LAYOUT,
      placement: { [panelA]: "center", [panelB]: "center" },
      order: { center: [panelA, panelB] },
      // task-a is the active tab in the center section (e.g. selected via the tab bar);
      // it is not necessarily the routed agent, so route navigation won't reassign it.
      activePanel: { center: panelA },
    });
    store.set(agentDeleteTargetAtom, { id: "task-a", name: "Agent A" });

    renderWithProviders(<AgentDeleteConfirmation />, { store });
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));

    const layout = store.get(workspaceLayoutAtom);
    expect(layout.order.center).toEqual([panelB]);
    expect(layout.placement[panelA]).toBeUndefined();
    // The section keeps a selected tab (the sibling), rather than dropping to empty.
    expect(layout.activePanel.center).toBe(panelB);
  });
});
