import type { RenderHookResult } from "@testing-library/react";
import { act, renderHook } from "@testing-library/react";
import { createStore } from "jotai";
import { Provider } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { CustomAction, CustomActionGroup, UserConfig } from "~/api";
import { userConfigAtom } from "~/common/state/atoms/userConfig.ts";

import { useCustomActions } from "./useCustomActions";

// Mock the API SDK functions used by useUserConfig.
const { mockUpdateUserConfig } = vi.hoisted(() => ({
  mockUpdateUserConfig: vi.fn(),
}));

vi.mock("../../../api", async (importOriginal) => {
  const original = await importOriginal();
  return {
    ...(original as object),
    getUserConfig: vi.fn().mockResolvedValue({ data: null }),
    updateUserConfig: mockUpdateUserConfig,
  };
});

// --- Test Utilities ---

const createAction = (overrides: Partial<CustomAction> = {}): CustomAction => ({
  id: crypto.randomUUID(),
  name: "Test Action",
  prompt: "Do something",
  autoSubmit: true,
  groupId: null,
  order: 0,
  ...overrides,
});

const createGroup = (overrides: Partial<CustomActionGroup> = {}): CustomActionGroup => ({
  id: crypto.randomUUID(),
  name: "Test Group",
  order: 0,
  ...overrides,
});

type UseCustomActionsResult = ReturnType<typeof useCustomActions>;

const renderCustomActions = (
  actions: Array<CustomAction> = [],
  groups: Array<CustomActionGroup> = [],
): RenderHookResult<UseCustomActionsResult, unknown> => {
  const store = createStore();
  store.set(userConfigAtom, { customActions: { actions, groups } } as UserConfig);

  const wrapper = ({ children }: { children: ReactNode }): ReactElement => (
    <Provider store={store}>{children}</Provider>
  );

  return renderHook(() => useCustomActions(), { wrapper });
};

// --- Tests ---

beforeEach(() => {
  vi.clearAllMocks();
  // Echo back the partial config that useUserConfig sends to the API. This
  // makes the optimistic update stick (instead of being reverted in the
  // catch block). The real backend returns the merged full config, but for
  // these tests the partial echo is enough to keep customActions populated.
  mockUpdateUserConfig.mockImplementation((options: { body: { userConfig: Record<string, unknown> } }) =>
    Promise.resolve({ data: options.body.userConfig }),
  );
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("useCustomActions", () => {
  describe("initial state", () => {
    it("returns empty arrays when no actions or groups exist", () => {
      const { result } = renderCustomActions();
      expect(result.current.actions).toEqual([]);
      expect(result.current.groups).toEqual([]);
    });

    it("returns actions when they exist in config", () => {
      const action = createAction({ name: "My Action" });
      const { result } = renderCustomActions([action]);
      expect(result.current.actions).toHaveLength(1);
      expect(result.current.actions[0].name).toBe("My Action");
    });

    it("returns groups when they exist in config", () => {
      const group = createGroup({ name: "My Group" });
      const { result } = renderCustomActions([], [group]);
      expect(result.current.groups).toHaveLength(1);
      expect(result.current.groups[0].name).toBe("My Group");
    });
  });

  describe("getActionsInGroup", () => {
    it("returns actions belonging to a specific group sorted by order", () => {
      const group = createGroup({ id: "g1" });
      const a1 = createAction({ name: "B", groupId: "g1", order: 1 });
      const a2 = createAction({ name: "A", groupId: "g1", order: 0 });
      const a3 = createAction({ name: "C", groupId: null, order: 0 });

      const { result } = renderCustomActions([a1, a2, a3], [group]);
      const groupActions = result.current.getActionsInGroup("g1");

      expect(groupActions).toHaveLength(2);
      expect(groupActions[0].name).toBe("A");
      expect(groupActions[1].name).toBe("B");
    });

    it("returns empty array for group with no actions", () => {
      const group = createGroup({ id: "g1" });
      const { result } = renderCustomActions([], [group]);
      expect(result.current.getActionsInGroup("g1")).toEqual([]);
    });
  });

  describe("getUngroupedActions", () => {
    it("returns actions with no groupId sorted by order", () => {
      const a1 = createAction({ name: "B", groupId: null, order: 1 });
      const a2 = createAction({ name: "A", groupId: null, order: 0 });
      const a3 = createAction({ name: "C", groupId: "g1", order: 0 });

      const { result } = renderCustomActions([a1, a2, a3]);
      const ungrouped = result.current.getUngroupedActions();

      expect(ungrouped).toHaveLength(2);
      expect(ungrouped[0].name).toBe("A");
      expect(ungrouped[1].name).toBe("B");
    });

    it("returns empty array when all actions are grouped", () => {
      const a1 = createAction({ groupId: "g1" });
      const { result } = renderCustomActions([a1]);
      expect(result.current.getUngroupedActions()).toEqual([]);
    });
  });

  describe("getSortedGroups", () => {
    it("returns groups sorted by order", () => {
      const g1 = createGroup({ name: "Second", order: 1 });
      const g2 = createGroup({ name: "First", order: 0 });
      const g3 = createGroup({ name: "Third", order: 2 });

      const { result } = renderCustomActions([], [g1, g2, g3]);
      const sorted = result.current.getSortedGroups();

      expect(sorted).toHaveLength(3);
      expect(sorted[0].name).toBe("First");
      expect(sorted[1].name).toBe("Second");
      expect(sorted[2].name).toBe("Third");
    });
  });

  describe("addAction", () => {
    it("adds an action with generated id and correct order", async () => {
      const { result } = renderCustomActions();

      await act(async () => {
        await result.current.addAction({
          name: "New Action",
          prompt: "Do the thing",
          autoSubmit: true,
          groupId: null,
        });
      });

      expect(result.current.actions).toHaveLength(1);
      expect(result.current.actions[0].name).toBe("New Action");
      expect(result.current.actions[0].prompt).toBe("Do the thing");
      expect(result.current.actions[0].id).toBeTruthy();
      expect(result.current.actions[0].order).toBe(0);
    });

    it("adds action with correct order when group already has actions", async () => {
      const existing = createAction({ name: "Existing", groupId: "g1", order: 0 });
      const group = createGroup({ id: "g1" });
      const { result } = renderCustomActions([existing], [group]);

      await act(async () => {
        await result.current.addAction({
          name: "New Action",
          prompt: "Do more",
          autoSubmit: false,
          groupId: "g1",
        });
      });

      expect(result.current.actions).toHaveLength(2);
      const newAction = result.current.actions.find((a) => a.name === "New Action");
      expect(newAction).toBeTruthy();
      expect(newAction!.order).toBe(1);
      expect(newAction!.groupId).toBe("g1");
    });

    it("adds ungrouped action with correct order among ungrouped", async () => {
      const existing1 = createAction({ name: "First", groupId: null, order: 0 });
      const existing2 = createAction({ name: "Second", groupId: null, order: 1 });
      const { result } = renderCustomActions([existing1, existing2]);

      await act(async () => {
        await result.current.addAction({
          name: "Third",
          prompt: "Three",
          autoSubmit: true,
          groupId: null,
        });
      });

      expect(result.current.actions).toHaveLength(3);
      const newAction = result.current.actions.find((a) => a.name === "Third");
      expect(newAction!.order).toBe(2);
    });
  });

  describe("addActionWithNewGroup", () => {
    it("creates both a new group and a new action atomically", async () => {
      const { result } = renderCustomActions();

      await act(async () => {
        await result.current.addActionWithNewGroup(
          { name: "Action in New Group", prompt: "Do it", autoSubmit: true },
          "Brand New Group",
        );
      });

      expect(result.current.actions).toHaveLength(1);
      expect(result.current.groups).toHaveLength(1);
      expect(result.current.groups[0].name).toBe("Brand New Group");
      expect(result.current.actions[0].groupId).toBe(result.current.groups[0].id);
      expect(result.current.actions[0].order).toBe(0);
    });

    it("assigns correct order to new group among existing groups", async () => {
      const existingGroup = createGroup({ name: "Existing", order: 0 });
      const { result } = renderCustomActions([], [existingGroup]);

      await act(async () => {
        await result.current.addActionWithNewGroup({ name: "Action", prompt: "Prompt", autoSubmit: true }, "New Group");
      });

      const newGroup = result.current.groups.find((g) => g.name === "New Group");
      expect(newGroup!.order).toBe(1);
    });
  });

  describe("updateAction", () => {
    it("updates an existing action's fields", async () => {
      const action = createAction({ id: "a1", name: "Old Name", prompt: "Old prompt" });
      const { result } = renderCustomActions([action]);

      await act(async () => {
        await result.current.updateAction({
          ...action,
          name: "New Name",
          prompt: "New prompt",
        });
      });

      expect(result.current.actions).toHaveLength(1);
      expect(result.current.actions[0].name).toBe("New Name");
      expect(result.current.actions[0].prompt).toBe("New prompt");
    });

    it("does not modify other actions", async () => {
      const a1 = createAction({ id: "a1", name: "Action 1" });
      const a2 = createAction({ id: "a2", name: "Action 2" });
      const { result } = renderCustomActions([a1, a2]);

      await act(async () => {
        await result.current.updateAction({ ...a1, name: "Updated" });
      });

      expect(result.current.actions.find((a) => a.id === "a2")!.name).toBe("Action 2");
    });
  });

  describe("updateActionWithNewGroup", () => {
    it("updates an action and creates a new group simultaneously", async () => {
      const action = createAction({ id: "a1", name: "Action", groupId: null });
      const { result } = renderCustomActions([action]);

      await act(async () => {
        await result.current.updateActionWithNewGroup({ ...action, name: "Updated Action" }, "New Group");
      });

      expect(result.current.groups).toHaveLength(1);
      expect(result.current.groups[0].name).toBe("New Group");
      expect(result.current.actions[0].groupId).toBe(result.current.groups[0].id);
    });
  });

  describe("deleteAction", () => {
    it("removes an action by id", async () => {
      const a1 = createAction({ id: "a1", name: "Keep" });
      const a2 = createAction({ id: "a2", name: "Delete" });
      const { result } = renderCustomActions([a1, a2]);

      await act(async () => {
        await result.current.deleteAction("a2");
      });

      expect(result.current.actions).toHaveLength(1);
      expect(result.current.actions[0].name).toBe("Keep");
    });

    it("recomputes orders in the same group after deletion", async () => {
      const a1 = createAction({ id: "a1", groupId: "g1", order: 0 });
      const a2 = createAction({ id: "a2", groupId: "g1", order: 1 });
      const a3 = createAction({ id: "a3", groupId: "g1", order: 2 });
      const group = createGroup({ id: "g1" });
      const { result } = renderCustomActions([a1, a2, a3], [group]);

      await act(async () => {
        await result.current.deleteAction("a2");
      });

      const remaining = result.current.getActionsInGroup("g1");
      expect(remaining).toHaveLength(2);
      expect(remaining[0].order).toBe(0);
      expect(remaining[1].order).toBe(1);
    });

    it("does nothing when action id is not found", async () => {
      const a1 = createAction({ id: "a1" });
      const { result } = renderCustomActions([a1]);

      await act(async () => {
        await result.current.deleteAction("nonexistent");
      });

      expect(result.current.actions).toHaveLength(1);
    });

    it("does not affect actions in other groups", async () => {
      const a1 = createAction({ id: "a1", groupId: "g1", order: 0 });
      const a2 = createAction({ id: "a2", groupId: "g2", order: 0 });
      const g1 = createGroup({ id: "g1" });
      const g2 = createGroup({ id: "g2" });
      const { result } = renderCustomActions([a1, a2], [g1, g2]);

      await act(async () => {
        await result.current.deleteAction("a1");
      });

      expect(result.current.getActionsInGroup("g2")).toHaveLength(1);
      expect(result.current.getActionsInGroup("g2")[0].order).toBe(0);
    });
  });

  describe("addGroup", () => {
    it("adds a group and returns its id", async () => {
      const { result } = renderCustomActions();
      let groupId: string = "";

      await act(async () => {
        groupId = await result.current.addGroup("New Group");
      });

      expect(groupId).toBeTruthy();
      expect(result.current.groups).toHaveLength(1);
      expect(result.current.groups[0].name).toBe("New Group");
      expect(result.current.groups[0].id).toBe(groupId);
    });

    it("assigns correct order to new groups", async () => {
      const g1 = createGroup({ order: 0 });
      const g2 = createGroup({ order: 1 });
      const { result } = renderCustomActions([], [g1, g2]);

      await act(async () => {
        await result.current.addGroup("Third Group");
      });

      const newGroup = result.current.groups.find((g) => g.name === "Third Group");
      expect(newGroup!.order).toBe(2);
    });
  });

  describe("renameGroup", () => {
    it("renames a group by id", async () => {
      const group = createGroup({ id: "g1", name: "Old Name" });
      const { result } = renderCustomActions([], [group]);

      await act(async () => {
        await result.current.renameGroup("g1", "New Name");
      });

      expect(result.current.groups[0].name).toBe("New Name");
    });

    it("does not affect other groups", async () => {
      const g1 = createGroup({ id: "g1", name: "Group 1" });
      const g2 = createGroup({ id: "g2", name: "Group 2" });
      const { result } = renderCustomActions([], [g1, g2]);

      await act(async () => {
        await result.current.renameGroup("g1", "Renamed");
      });

      expect(result.current.groups.find((g) => g.id === "g2")!.name).toBe("Group 2");
    });
  });

  describe("deleteGroup", () => {
    it("removes the group and its actions", async () => {
      const group = createGroup({ id: "g1", name: "Doomed" });
      const a1 = createAction({ id: "a1", groupId: "g1", order: 0 });
      const a2 = createAction({ id: "a2", groupId: "g1", order: 1 });
      const { result } = renderCustomActions([a1, a2], [group]);

      await act(async () => {
        await result.current.deleteGroup("g1");
      });

      expect(result.current.groups).toHaveLength(0);
      expect(result.current.actions).toHaveLength(0);
    });

    it("only deletes actions belonging to the deleted group", async () => {
      const group = createGroup({ id: "g1" });
      const a1 = createAction({ id: "a1", groupId: "g1", name: "Grouped" });
      const a2 = createAction({ id: "a2", groupId: null, name: "Ungrouped" });
      const { result } = renderCustomActions([a1, a2], [group]);

      await act(async () => {
        await result.current.deleteGroup("g1");
      });

      expect(result.current.actions).toHaveLength(1);
      expect(result.current.actions[0].name).toBe("Ungrouped");
    });

    it("preserves ungrouped actions when deleting a group", async () => {
      const group = createGroup({ id: "g1" });
      const ungrouped = createAction({ id: "u1", groupId: null, order: 0 });
      const grouped1 = createAction({ id: "a1", groupId: "g1", order: 0 });
      const grouped2 = createAction({ id: "a2", groupId: "g1", order: 1 });
      const { result } = renderCustomActions([ungrouped, grouped1, grouped2], [group]);

      await act(async () => {
        await result.current.deleteGroup("g1");
      });

      const allUngrouped = result.current.getUngroupedActions();
      expect(allUngrouped).toHaveLength(1);
      expect(allUngrouped[0].id).toBe("u1");
      expect(allUngrouped[0].order).toBe(0);
    });

    it("recomputes order of remaining groups", async () => {
      const g1 = createGroup({ id: "g1", order: 0 });
      const g2 = createGroup({ id: "g2", order: 1 });
      const g3 = createGroup({ id: "g3", order: 2 });
      const { result } = renderCustomActions([], [g1, g2, g3]);

      await act(async () => {
        await result.current.deleteGroup("g2");
      });

      const sorted = result.current.getSortedGroups();
      expect(sorted).toHaveLength(2);
      expect(sorted[0].id).toBe("g1");
      expect(sorted[0].order).toBe(0);
      expect(sorted[1].id).toBe("g3");
      expect(sorted[1].order).toBe(1);
    });
  });

  describe("moveActionToGroup", () => {
    it("moves an action from ungrouped to a group", async () => {
      const group = createGroup({ id: "g1" });
      const action = createAction({ id: "a1", groupId: null, order: 0 });
      const { result } = renderCustomActions([action], [group]);

      await act(async () => {
        await result.current.moveActionToGroup("a1", "g1");
      });

      expect(result.current.actions[0].groupId).toBe("g1");
    });

    it("moves an action from a group to ungrouped", async () => {
      const group = createGroup({ id: "g1" });
      const action = createAction({ id: "a1", groupId: "g1", order: 0 });
      const { result } = renderCustomActions([action], [group]);

      await act(async () => {
        await result.current.moveActionToGroup("a1", null);
      });

      expect(result.current.actions[0].groupId).toBeNull();
    });

    it("moves an action between groups", async () => {
      const g1 = createGroup({ id: "g1" });
      const g2 = createGroup({ id: "g2" });
      const action = createAction({ id: "a1", groupId: "g1", order: 0 });
      const { result } = renderCustomActions([action], [g1, g2]);

      await act(async () => {
        await result.current.moveActionToGroup("a1", "g2");
      });

      expect(result.current.actions[0].groupId).toBe("g2");
    });

    it("recomputes orders in old group after move", async () => {
      const group = createGroup({ id: "g1" });
      const a1 = createAction({ id: "a1", groupId: "g1", order: 0 });
      const a2 = createAction({ id: "a2", groupId: "g1", order: 1 });
      const a3 = createAction({ id: "a3", groupId: "g1", order: 2 });
      const { result } = renderCustomActions([a1, a2, a3], [group]);

      await act(async () => {
        await result.current.moveActionToGroup("a2", null);
      });

      const remaining = result.current.getActionsInGroup("g1");
      expect(remaining).toHaveLength(2);
      expect(remaining[0].order).toBe(0);
      expect(remaining[1].order).toBe(1);
    });

    it("does nothing if action is not found", async () => {
      const { result } = renderCustomActions();

      await act(async () => {
        await result.current.moveActionToGroup("nonexistent", "g1");
      });

      expect(result.current.actions).toHaveLength(0);
    });
  });

  describe("reorderActions", () => {
    describe("within-group reorder", () => {
      it("moves an action to a different position within the same group", async () => {
        const group = createGroup({ id: "g1" });
        const a1 = createAction({ id: "a1", name: "First", groupId: "g1", order: 0 });
        const a2 = createAction({ id: "a2", name: "Second", groupId: "g1", order: 1 });
        const a3 = createAction({ id: "a3", name: "Third", groupId: "g1", order: 2 });
        const { result } = renderCustomActions([a1, a2, a3], [group]);

        // Move "First" to position 2 (after "Third")
        await act(async () => {
          await result.current.reorderActions("a1", 2);
        });

        const groupActions = result.current.getActionsInGroup("g1");
        expect(groupActions[0].id).toBe("a2");
        expect(groupActions[1].id).toBe("a3");
        expect(groupActions[2].id).toBe("a1");
      });

      it("moves an action from end to beginning", async () => {
        const a1 = createAction({ id: "a1", name: "First", groupId: null, order: 0 });
        const a2 = createAction({ id: "a2", name: "Second", groupId: null, order: 1 });
        const a3 = createAction({ id: "a3", name: "Third", groupId: null, order: 2 });
        const { result } = renderCustomActions([a1, a2, a3]);

        await act(async () => {
          await result.current.reorderActions("a3", 0);
        });

        const actions = result.current.getUngroupedActions();
        expect(actions[0].id).toBe("a3");
        expect(actions[1].id).toBe("a1");
        expect(actions[2].id).toBe("a2");
      });

      it("handles moving to position beyond array length", async () => {
        const a1 = createAction({ id: "a1", groupId: null, order: 0 });
        const a2 = createAction({ id: "a2", groupId: null, order: 1 });
        const { result } = renderCustomActions([a1, a2]);

        await act(async () => {
          await result.current.reorderActions("a1", 999);
        });

        const actions = result.current.getUngroupedActions();
        expect(actions[0].id).toBe("a2");
        expect(actions[1].id).toBe("a1");
      });

      it("reassigns clean sequential orders", async () => {
        const a1 = createAction({ id: "a1", groupId: null, order: 0 });
        const a2 = createAction({ id: "a2", groupId: null, order: 5 });
        const a3 = createAction({ id: "a3", groupId: null, order: 10 });
        const { result } = renderCustomActions([a1, a2, a3]);

        await act(async () => {
          await result.current.reorderActions("a3", 1);
        });

        const actions = result.current.getUngroupedActions();
        expect(actions[0].order).toBe(0);
        expect(actions[1].order).toBe(1);
        expect(actions[2].order).toBe(2);
      });
    });

    describe("cross-group reorder", () => {
      it("moves an action from one group to another at a specified position", async () => {
        const g1 = createGroup({ id: "g1" });
        const g2 = createGroup({ id: "g2" });
        const a1 = createAction({ id: "a1", name: "Source", groupId: "g1", order: 0 });
        const a2 = createAction({ id: "a2", name: "Target First", groupId: "g2", order: 0 });
        const a3 = createAction({ id: "a3", name: "Target Second", groupId: "g2", order: 1 });
        const { result } = renderCustomActions([a1, a2, a3], [g1, g2]);

        // Move a1 from g1 to g2 at position 1 (between the two g2 actions)
        await act(async () => {
          await result.current.reorderActions("a1", 1, "g2");
        });

        expect(result.current.getActionsInGroup("g1")).toHaveLength(0);
        const g2Actions = result.current.getActionsInGroup("g2");
        expect(g2Actions).toHaveLength(3);
        expect(g2Actions[0].id).toBe("a2");
        expect(g2Actions[1].id).toBe("a1");
        expect(g2Actions[2].id).toBe("a3");
      });

      it("moves an action from group to ungrouped", async () => {
        const group = createGroup({ id: "g1" });
        const a1 = createAction({ id: "a1", groupId: "g1", order: 0 });
        const a2 = createAction({ id: "a2", groupId: null, order: 0 });
        const { result } = renderCustomActions([a1, a2], [group]);

        await act(async () => {
          await result.current.reorderActions("a1", 0, null);
        });

        expect(result.current.getActionsInGroup("g1")).toHaveLength(0);
        expect(result.current.getUngroupedActions()).toHaveLength(2);
      });

      it("moves an action from ungrouped to a group", async () => {
        const group = createGroup({ id: "g1" });
        const a1 = createAction({ id: "a1", groupId: null, order: 0 });
        const { result } = renderCustomActions([a1], [group]);

        await act(async () => {
          await result.current.reorderActions("a1", 0, "g1");
        });

        expect(result.current.getUngroupedActions()).toHaveLength(0);
        expect(result.current.getActionsInGroup("g1")).toHaveLength(1);
      });

      it("recomputes orders in old group after cross-group move", async () => {
        const g1 = createGroup({ id: "g1" });
        const g2 = createGroup({ id: "g2" });
        const a1 = createAction({ id: "a1", groupId: "g1", order: 0 });
        const a2 = createAction({ id: "a2", groupId: "g1", order: 1 });
        const a3 = createAction({ id: "a3", groupId: "g1", order: 2 });
        const { result } = renderCustomActions([a1, a2, a3], [g1, g2]);

        // Move middle action to g2
        await act(async () => {
          await result.current.reorderActions("a2", 0, "g2");
        });

        const g1Actions = result.current.getActionsInGroup("g1");
        expect(g1Actions).toHaveLength(2);
        expect(g1Actions[0].order).toBe(0);
        expect(g1Actions[1].order).toBe(1);
      });
    });

    it("does nothing when action is not found", async () => {
      const a1 = createAction({ id: "a1" });
      const { result } = renderCustomActions([a1]);

      await act(async () => {
        await result.current.reorderActions("nonexistent", 0);
      });

      expect(result.current.actions).toHaveLength(1);
    });
  });

  describe("reorderGroups", () => {
    it("moves a group to a different position", async () => {
      const g1 = createGroup({ id: "g1", name: "First", order: 0 });
      const g2 = createGroup({ id: "g2", name: "Second", order: 1 });
      const g3 = createGroup({ id: "g3", name: "Third", order: 2 });
      const { result } = renderCustomActions([], [g1, g2, g3]);

      await act(async () => {
        await result.current.reorderGroups("g3", 0);
      });

      const sorted = result.current.getSortedGroups();
      expect(sorted[0].id).toBe("g3");
      expect(sorted[1].id).toBe("g1");
      expect(sorted[2].id).toBe("g2");
    });

    it("reassigns clean sequential orders", async () => {
      const g1 = createGroup({ id: "g1", order: 0 });
      const g2 = createGroup({ id: "g2", order: 5 });
      const g3 = createGroup({ id: "g3", order: 10 });
      const { result } = renderCustomActions([], [g1, g2, g3]);

      await act(async () => {
        await result.current.reorderGroups("g1", 2);
      });

      const sorted = result.current.getSortedGroups();
      expect(sorted[0].order).toBe(0);
      expect(sorted[1].order).toBe(1);
      expect(sorted[2].order).toBe(2);
    });

    it("does nothing when group is not found", async () => {
      const g1 = createGroup({ id: "g1", order: 0 });
      const { result } = renderCustomActions([], [g1]);

      await act(async () => {
        await result.current.reorderGroups("nonexistent", 0);
      });

      expect(result.current.groups).toHaveLength(1);
    });
  });

  describe("importActions", () => {
    it("imports actions and groups with new ids", async () => {
      const { result } = renderCustomActions();

      const importedGroup = createGroup({ id: "old-g1", name: "Imported Group", order: 0 });
      const importedAction = createAction({
        id: "old-a1",
        name: "Imported Action",
        groupId: "old-g1",
        order: 0,
      });

      await act(async () => {
        await result.current.importActions([importedAction], [importedGroup]);
      });

      expect(result.current.groups).toHaveLength(1);
      expect(result.current.actions).toHaveLength(1);
      // IDs should be regenerated
      expect(result.current.groups[0].id).not.toBe("old-g1");
      expect(result.current.actions[0].id).not.toBe("old-a1");
      // Group reference should be updated
      expect(result.current.actions[0].groupId).toBe(result.current.groups[0].id);
    });

    it("preserves existing actions and groups", async () => {
      const existingAction = createAction({ id: "e1", name: "Existing" });
      const existingGroup = createGroup({ id: "eg1", name: "Existing Group" });
      const { result } = renderCustomActions([existingAction], [existingGroup]);

      const importedAction = createAction({ name: "Imported" });
      const importedGroup = createGroup({ name: "Imported Group" });

      await act(async () => {
        await result.current.importActions([importedAction], [importedGroup]);
      });

      expect(result.current.actions).toHaveLength(2);
      expect(result.current.groups).toHaveLength(2);
    });

    it("assigns correct orders to imported items", async () => {
      const existingGroup = createGroup({ order: 0 });
      const existingAction = createAction({ groupId: null, order: 0 });
      const { result } = renderCustomActions([existingAction], [existingGroup]);

      const importedGroup = createGroup({ order: 0 });
      const importedAction = createAction({ groupId: null, order: 0 });

      await act(async () => {
        await result.current.importActions([importedAction], [importedGroup]);
      });

      const newGroup = result.current.groups.find((g) => g.id !== existingGroup.id);
      expect(newGroup!.order).toBe(1);

      // Imported ungrouped action should get next order
      const ungrouped = result.current.getUngroupedActions();
      expect(ungrouped).toHaveLength(2);
      expect(ungrouped[0].order).toBe(0);
      expect(ungrouped[1].order).toBe(1);
    });

    it("maps group references for imported actions correctly", async () => {
      const g1 = createGroup({ id: "import-g1", name: "Group A", order: 0 });
      const g2 = createGroup({ id: "import-g2", name: "Group B", order: 1 });
      const a1 = createAction({ id: "import-a1", groupId: "import-g1", order: 0 });
      const a2 = createAction({ id: "import-a2", groupId: "import-g2", order: 0 });
      const a3 = createAction({ id: "import-a3", groupId: null, order: 0 });

      const { result } = renderCustomActions();

      await act(async () => {
        await result.current.importActions([a1, a2, a3], [g1, g2]);
      });

      // All grouped actions should reference new group ids
      const groupA = result.current.groups.find((g) => g.name === "Group A")!;
      const groupB = result.current.groups.find((g) => g.name === "Group B")!;

      const actionsInA = result.current.getActionsInGroup(groupA.id);
      const actionsInB = result.current.getActionsInGroup(groupB.id);
      const ungrouped = result.current.getUngroupedActions();

      expect(actionsInA).toHaveLength(1);
      expect(actionsInB).toHaveLength(1);
      expect(ungrouped).toHaveLength(1);
    });
  });
});
