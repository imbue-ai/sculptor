import { useAtomValue } from "jotai";
import { useCallback, useMemo } from "react";

import type { CustomAction, CustomActionGroup, CustomActionsConfig } from "~/api";
import { isBuiltInAction, isBuiltInGroup } from "~/common/utils/builtinActions.ts";

import { customActionsAtom } from "../atoms/userConfig.ts";
import { useUserConfig } from "./useUserConfig.ts";

type UseCustomActionsResult = {
  config: CustomActionsConfig;
  actions: ReadonlyArray<CustomAction>;
  groups: ReadonlyArray<CustomActionGroup>;
  addAction: (action: Omit<CustomAction, "id" | "order">) => Promise<void>;
  addActionWithNewGroup: (action: Omit<CustomAction, "id" | "order" | "groupId">, groupName: string) => Promise<void>;
  updateAction: (action: CustomAction) => Promise<void>;
  updateActionWithNewGroup: (action: CustomAction, groupName: string) => Promise<void>;
  deleteAction: (actionId: string) => Promise<void>;
  addGroup: (name: string) => Promise<string>;
  renameGroup: (groupId: string, name: string) => Promise<void>;
  deleteGroup: (groupId: string) => Promise<void>;
  moveActionToGroup: (actionId: string, groupId: string | null) => Promise<void>;
  reorderActions: (actionId: string, newOrder: number, newGroupId?: string | null) => Promise<void>;
  reorderGroups: (groupId: string, newOrder: number) => Promise<void>;
  getActionsInGroup: (groupId: string) => ReadonlyArray<CustomAction>;
  getUngroupedActions: () => ReadonlyArray<CustomAction>;
  getSortedGroups: () => ReadonlyArray<CustomActionGroup>;
  importActions: (importedActions: Array<CustomAction>, importedGroups: Array<CustomActionGroup>) => Promise<void>;
};

const getNextOrder = (items: ReadonlyArray<{ order?: number }>): number => {
  if (items.length === 0) return 0;
  return Math.max(...items.map((item) => item.order ?? 0)) + 1;
};

const recomputeOrders = <T extends { order?: number }>(items: Array<T>): Array<T> => {
  return items.sort((a, b) => (a.order ?? 0) - (b.order ?? 0)).map((item, index) => ({ ...item, order: index }));
};

export const useCustomActions = (): UseCustomActionsResult => {
  const config = useAtomValue(customActionsAtom);
  const { updateConfig } = useUserConfig();

  const actions = useMemo(() => config.actions ?? [], [config.actions]);
  const groups = useMemo(() => config.groups ?? [], [config.groups]);

  const getActionsInGroup = useCallback(
    (groupId: string): ReadonlyArray<CustomAction> => {
      return [...actions.filter((a) => a.groupId === groupId)].sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
    },
    [actions],
  );

  const getUngroupedActions = useCallback((): ReadonlyArray<CustomAction> => {
    return [...actions.filter((a) => !a.groupId)].sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
  }, [actions]);

  const getSortedGroups = useCallback((): ReadonlyArray<CustomActionGroup> => {
    return [...groups].sort((a, b) => a.order - b.order);
  }, [groups]);

  const persistConfig = useCallback(
    async (newActions: Array<CustomAction>, newGroups: Array<CustomActionGroup>): Promise<void> => {
      await updateConfig({
        customActions: { actions: newActions, groups: newGroups },
      });
    },
    [updateConfig],
  );

  const addAction = useCallback(
    async (action: Omit<CustomAction, "id" | "order">): Promise<void> => {
      if (isBuiltInGroup(action.groupId)) return;
      const targetGroupActions = actions.filter((a) => (action.groupId ? a.groupId === action.groupId : !a.groupId));
      const newAction = {
        ...action,
        id: crypto.randomUUID(),
        order: getNextOrder(targetGroupActions),
      } as CustomAction;
      await persistConfig([...actions, newAction], [...groups]);
    },
    [actions, groups, persistConfig],
  );

  const addActionWithNewGroup = useCallback(
    async (action: Omit<CustomAction, "id" | "order" | "groupId">, groupName: string): Promise<void> => {
      const newGroup: CustomActionGroup = {
        id: crypto.randomUUID(),
        name: groupName,
        order: getNextOrder(groups),
      };
      const newAction = {
        ...action,
        id: crypto.randomUUID(),
        groupId: newGroup.id,
        order: 0,
      } as CustomAction;
      await persistConfig([...actions, newAction], [...groups, newGroup]);
    },
    [actions, groups, persistConfig],
  );

  const updateAction = useCallback(
    async (action: CustomAction): Promise<void> => {
      if (isBuiltInAction(action.id)) return;
      const newActions = actions.map((a) => (a.id === action.id ? action : a));
      await persistConfig([...newActions], [...groups]);
    },
    [actions, groups, persistConfig],
  );

  const updateActionWithNewGroup = useCallback(
    async (action: CustomAction, groupName: string): Promise<void> => {
      if (isBuiltInAction(action.id)) return;
      const newGroup: CustomActionGroup = {
        id: crypto.randomUUID(),
        name: groupName,
        order: getNextOrder(groups),
      };
      const updatedAction = { ...action, groupId: newGroup.id };
      const newActions = actions.map((a) => (a.id === updatedAction.id ? updatedAction : a));
      await persistConfig(newActions, [...groups, newGroup]);
    },
    [actions, groups, persistConfig],
  );

  const deleteAction = useCallback(
    async (actionId: string): Promise<void> => {
      if (isBuiltInAction(actionId)) return;
      const action = actions.find((a) => a.id === actionId);
      if (!action) return;
      const remaining = actions.filter((a) => a.id !== actionId);
      const sameGroupActions = remaining.filter((a) => (action.groupId ? a.groupId === action.groupId : !a.groupId));
      const reordered = recomputeOrders([...sameGroupActions]);
      const newActions = remaining.map((a) => {
        const reorderedMatch = reordered.find((r) => r.id === a.id);
        return reorderedMatch ?? a;
      });
      await persistConfig(newActions, [...groups]);
    },
    [actions, groups, persistConfig],
  );

  const addGroup = useCallback(
    async (name: string): Promise<string> => {
      const newGroup: CustomActionGroup = {
        id: crypto.randomUUID(),
        name,
        order: getNextOrder(groups),
      };
      await persistConfig([...actions], [...groups, newGroup]);
      return newGroup.id;
    },
    [actions, groups, persistConfig],
  );

  const renameGroup = useCallback(
    async (groupId: string, name: string): Promise<void> => {
      if (isBuiltInGroup(groupId)) return;
      const newGroups = groups.map((g) => (g.id === groupId ? { ...g, name } : g));
      await persistConfig([...actions], [...newGroups]);
    },
    [actions, groups, persistConfig],
  );

  const deleteGroup = useCallback(
    async (groupId: string): Promise<void> => {
      if (isBuiltInGroup(groupId)) return;
      const newActions = actions.filter((a) => a.groupId !== groupId);
      const newGroups = recomputeOrders(groups.filter((g) => g.id !== groupId));
      await persistConfig(newActions, newGroups);
    },
    [actions, groups, persistConfig],
  );

  const moveActionToGroup = useCallback(
    async (actionId: string, groupId: string | null): Promise<void> => {
      if (isBuiltInAction(actionId) || isBuiltInGroup(groupId)) return;
      const action = actions.find((a) => a.id === actionId);
      if (!action) return;

      const targetGroupActions = actions.filter(
        (a) => a.id !== actionId && (groupId ? a.groupId === groupId : !a.groupId),
      );
      const newOrder = getNextOrder(targetGroupActions);

      // Recompute orders in old group
      const oldGroupActions = actions.filter(
        (a) => a.id !== actionId && (action.groupId ? a.groupId === action.groupId : !a.groupId),
      );
      const reorderedOld = recomputeOrders([...oldGroupActions]);

      const newActions = actions.map((a) => {
        if (a.id === actionId) {
          return { ...a, groupId: groupId ?? null, order: newOrder };
        }
        const reorderedMatch = reorderedOld.find((r) => r.id === a.id);
        return reorderedMatch ?? a;
      });

      await persistConfig(newActions, [...groups]);
    },
    [actions, groups, persistConfig],
  );

  const reorderActions = useCallback(
    async (actionId: string, newOrder: number, newGroupId?: string | null): Promise<void> => {
      if (isBuiltInAction(actionId) || (newGroupId !== undefined && isBuiltInGroup(newGroupId))) return;
      const action = actions.find((a) => a.id === actionId);
      if (!action) return;

      const targetGroupId = newGroupId !== undefined ? newGroupId : action.groupId;
      const isSameGroup = (action.groupId ?? null) === (targetGroupId ?? null);

      let newActions = [...actions];

      if (isSameGroup) {
        // Within-group reorder
        const groupActions = newActions
          .filter((a) => (targetGroupId ? a.groupId === targetGroupId : !a.groupId))
          .sort((a, b) => (a.order ?? 0) - (b.order ?? 0));

        const currentIndex = groupActions.findIndex((a) => a.id === actionId);
        if (currentIndex === -1) return;

        groupActions.splice(currentIndex, 1);
        const insertAt = Math.min(newOrder, groupActions.length);
        groupActions.splice(insertAt, 0, action);

        const reordered = groupActions.map((a, i) => ({ ...a, order: i }));
        const reorderedMap = new Map(reordered.map((a) => [a.id, a]));
        newActions = newActions.map((a) => reorderedMap.get(a.id) ?? a);
      } else {
        // Cross-group move
        // Remove from old group and recompute
        const oldGroupActions = newActions
          .filter((a) => a.id !== actionId && (action.groupId ? a.groupId === action.groupId : !a.groupId))
          .sort((a, b) => (a.order ?? 0) - (b.order ?? 0))
          .map((a, i) => ({ ...a, order: i }));

        // Add to new group at position
        const targetGroupActions = newActions
          .filter((a) => (targetGroupId ? a.groupId === targetGroupId : !a.groupId))
          .sort((a, b) => (a.order ?? 0) - (b.order ?? 0));

        const insertAt = Math.min(newOrder, targetGroupActions.length);
        targetGroupActions.splice(insertAt, 0, { ...action, groupId: targetGroupId ?? null });
        const reorderedTarget = targetGroupActions.map((a, i) => ({ ...a, order: i }));

        const allReordered = new Map([
          ...oldGroupActions.map((a) => [a.id, a] as const),
          ...reorderedTarget.map((a) => [a.id, a] as const),
        ]);

        newActions = newActions.map((a) => allReordered.get(a.id) ?? a);
      }

      await persistConfig(newActions, [...groups]);
    },
    [actions, groups, persistConfig],
  );

  const reorderGroups = useCallback(
    async (groupId: string, newOrder: number): Promise<void> => {
      if (isBuiltInGroup(groupId)) return;
      // Exclude built-in groups from reordering; they are injected virtually and keep a fixed position.
      const userGroups = groups.filter((g) => !isBuiltInGroup(g.id));
      const sortedGroups = [...userGroups].sort((a, b) => a.order - b.order);
      const currentIndex = sortedGroups.findIndex((g) => g.id === groupId);
      if (currentIndex === -1) return;

      const [removed] = sortedGroups.splice(currentIndex, 1);
      const insertAt = Math.min(newOrder, sortedGroups.length);
      sortedGroups.splice(insertAt, 0, removed);

      const reordered = sortedGroups.map((g, i) => ({ ...g, order: i }));
      await persistConfig([...actions], reordered);
    },
    [actions, groups, persistConfig],
  );

  const importActions = useCallback(
    async (importedActions: Array<CustomAction>, importedGroups: Array<CustomActionGroup>): Promise<void> => {
      const groupIdMap = new Map<string, string>();
      let nextGroupOrder = getNextOrder(groups);
      const newGroups = importedGroups.map((group) => {
        const newId = crypto.randomUUID();
        groupIdMap.set(group.id, newId);
        const mapped = { ...group, id: newId, order: nextGroupOrder };
        nextGroupOrder++;
        return mapped;
      });

      const existingUngrouped = actions.filter((a) => !a.groupId);
      let nextUngroupedOrder = getNextOrder(existingUngrouped);
      const newActions = importedActions.map((action) => {
        const newGroupId = action.groupId ? (groupIdMap.get(action.groupId) ?? null) : null;
        const newAction: CustomAction = {
          ...action,
          id: crypto.randomUUID(),
          groupId: newGroupId,
          order: newGroupId === null ? nextUngroupedOrder++ : (action.order ?? 0),
        };
        return newAction;
      });

      await persistConfig([...actions, ...newActions], [...groups, ...newGroups]);
    },
    [actions, groups, persistConfig],
  );

  return useMemo(
    () => ({
      config,
      actions,
      groups,
      addAction,
      addActionWithNewGroup,
      updateAction,
      updateActionWithNewGroup,
      deleteAction,
      addGroup,
      renameGroup,
      deleteGroup,
      moveActionToGroup,
      reorderActions,
      reorderGroups,
      getActionsInGroup,
      getUngroupedActions,
      getSortedGroups,
      importActions,
    }),
    [
      config,
      actions,
      groups,
      addAction,
      addActionWithNewGroup,
      updateAction,
      updateActionWithNewGroup,
      deleteAction,
      addGroup,
      renameGroup,
      deleteGroup,
      moveActionToGroup,
      reorderActions,
      reorderGroups,
      getActionsInGroup,
      getUngroupedActions,
      getSortedGroups,
      importActions,
    ],
  );
};
