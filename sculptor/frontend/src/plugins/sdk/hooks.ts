import { useAtom, useAtomValue } from "jotai";
import { atomFamily, atomWithStorage } from "jotai/utils";
import { useParams } from "react-router-dom";

import type { CodingAgentTaskView, Workspace } from "~/api";
import { tasksArrayAtom } from "~/common/state/atoms/tasks.ts";
import { workspacesArrayAtom } from "~/common/state/atoms/workspaces.ts";
import { useWorkspaceBranch as useHostWorkspaceBranch } from "~/common/state/hooks/useWorkspaceBranch.ts";

import { usePluginContext } from "../PluginContext.tsx";
import { useWorkspacePluginContext } from "../WorkspaceContext.tsx";

/** Current workspace id, read from the host-provided plugin context. */
export const useWorkspaceId = (): string => useWorkspacePluginContext().workspaceId;

/**
 * Every non-deleted workspace known to the host, or `undefined` until the
 * first batch has loaded. Unlike `useWorkspaceId`, this needs no workspace
 * context — it reads an app-global atom, so it works in an overlay (which
 * isn't bound to one workspace) as well as in a panel.
 */
export const useWorkspaces = (): ReadonlyArray<Workspace> | undefined => useAtomValue(workspacesArrayAtom);

/**
 * The id of the workspace the user is currently viewing, or `null` when the
 * route isn't a workspace page (settings, onboarding, etc.). Read straight
 * from the route, so it tracks navigation — the right "where am I" signal for
 * an app-global overlay.
 */
export const useCurrentWorkspaceId = (): string | null => {
  const { workspaceID } = useParams<{ workspaceID?: string }>();
  return workspaceID ?? null;
};

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
  if (tasks === undefined) return undefined;
  return tasks.filter((t) => t.workspaceId === workspaceId);
};
