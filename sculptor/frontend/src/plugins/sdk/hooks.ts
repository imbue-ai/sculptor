import { useAtom, useAtomValue } from "jotai";
import { atomFamily, atomWithStorage } from "jotai/utils";
import { useMemo } from "react";

import type { CodingAgentTaskView } from "~/api";
import { tasksArrayAtom } from "~/common/state/atoms/tasks.ts";
import { useWorkspaceBranch as useHostWorkspaceBranch } from "~/common/state/hooks/useWorkspaceBranch.ts";

import { usePluginContext } from "../PluginContext.tsx";
import { useWorkspacePluginContext } from "../WorkspaceContext.tsx";

/** Current workspace id, read from the host-provided plugin context. */
export const useWorkspaceId = (): string => useWorkspacePluginContext().workspaceId;

/**
 * The current git branch of the workspace the plugin is mounted in, or `null`
 * until the backend has reported it. Useful for linking the workspace to
 * external systems (e.g. parsing a ticket id out of the branch name).
 */
export const useWorkspaceBranch = (): string | null => {
  const { workspaceId } = useWorkspacePluginContext();
  return useHostWorkspaceBranch(workspaceId)?.currentBranch ?? null;
};

// One persisted atom per (plugin, key). atomFamily caches by the full storage
// key; getOnInit reads localStorage synchronously so the value is present on
// first render instead of flashing the default.
const pluginSettingAtomFamily = atomFamily((storageKey: string) =>
  atomWithStorage<string>(storageKey, "", undefined, { getOnInit: true }),
);

/**
 * A persisted string setting scoped to the calling plugin. Backed by
 * localStorage under a `sculptor-plugin:<id>:<key>` namespace and shared
 * reactively across the plugin's panel and its settings component.
 */
export const usePluginSetting = (key: string): [string, (value: string) => void] => {
  const { pluginId } = usePluginContext();
  return useAtom(pluginSettingAtomFamily(`sculptor-plugin:${pluginId}:${key}`));
};

/**
 * All non-deleted tasks for the workspace the plugin is mounted in. Returns
 * `undefined` until the host's task stream has produced its first batch.
 */
export const useWorkspaceTasks = (): ReadonlyArray<CodingAgentTaskView> | undefined => {
  const { workspaceId } = useWorkspacePluginContext();
  const tasks = useAtomValue(tasksArrayAtom);
  // Memoize so plugin authors get a stable array identity across renders (safe
  // to use as an effect/memo dependency); recomputes only when the host task
  // list or the workspace changes.
  return useMemo(() => tasks?.filter((t) => t.workspaceId === workspaceId), [tasks, workspaceId]);
};
