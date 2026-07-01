import { atom, useAtom, useAtomValue } from "jotai";
import { atomFamily, atomWithStorage, selectAtom } from "jotai/utils";
import { useContext, useEffect, useMemo, useRef } from "react";
import { useParams } from "react-router-dom";

import type { CodingAgentTaskView } from "~/api";
import { prStatusAtomFamily } from "~/common/state/atoms/prStatus.ts";
import { tasksArrayAtom } from "~/common/state/atoms/tasks.ts";
import { workspaceBranchAtomFamily } from "~/common/state/atoms/workspaceBranch.ts";
import { workspaceAtomFamily, workspacesArrayAtom } from "~/common/state/atoms/workspaces.ts";
import { useWorkspaceNavigation } from "~/common/state/hooks/useWorkspaceNavigation.ts";

import { usePluginContext } from "../PluginContext.tsx";
import { useWorkspacePluginContext, WorkspacePluginContext } from "../WorkspaceContext.tsx";

/**
 * A curated, plugin-facing view of a single workspace: identity, label, live git
 * branch, and code-host link. Deliberately a subset — not the host's full
 * `Workspace` model — so the plugin contract doesn't couple to backend
 * internals. The element type of `useWorkspaces` and the return of
 * `useCurrentWorkspace`, so a plugin reads the same shape whether it looks at
 * one workspace or all of them.
 */
export type WorkspaceView = {
  id: string;
  description: string;
  /** Live current branch, or `null` until the backend has reported it. */
  branch: string | null;
  targetBranch: string | null;
  /**
   * Web URL of the workspace's pull/merge request, or `null` when there is none
   * (or the backend hasn't reported PR status yet). The authoritative link
   * between a Sculptor workspace and an external code host — useful when the
   * branch name alone can't be resolved, since Sculptor-generated branch names
   * carry no issue identifier and no host-side VCS link.
   */
  pullRequestUrl: string | null;
};

/** @deprecated Use {@link WorkspaceView}; kept as an alias for the prior name. */
export type CurrentWorkspace = WorkspaceView;

// One derived view atom per workspace id, composing the workspace model with
// its live branch and PR status (which the host keeps in separate atoms) into
// the curated WorkspaceView shape. Shared by the single- and all-workspaces
// hooks so the curated mapping lives in exactly one place.
const workspaceViewAtomFamily = atomFamily((id: string) =>
  atom((get): WorkspaceView | null => {
    const workspace = get(workspaceAtomFamily(id));
    if (!workspace) return null;
    return {
      id: workspace.objectId,
      description: workspace.description,
      branch: get(workspaceBranchAtomFamily(id))?.currentBranch ?? null,
      targetBranch: workspace.targetBranch ?? null,
      pullRequestUrl: get(prStatusAtomFamily(id))?.prWebUrl ?? null,
    };
  }),
);

// The curated view of every non-deleted workspace, composed from the same
// per-id view atom so the all-workspaces list and the current-workspace hook
// can never report a workspace differently.
const allWorkspaceViewsAtom = atom((get): ReadonlyArray<WorkspaceView> | undefined => {
  const workspaces = get(workspacesArrayAtom);
  if (workspaces === undefined) return undefined;
  return workspaces
    .map((workspace) => get(workspaceViewAtomFamily(workspace.objectId)))
    .filter((view): view is WorkspaceView => view !== null);
});

/**
 * Every non-deleted workspace known to the host as a curated {@link
 * WorkspaceView} (including live branch and PR URL), or `undefined` until the
 * first batch has loaded. App-global: it needs no workspace context, so it
 * works in an overlay or home view as well as a panel.
 */
export const useWorkspaces = (): ReadonlyArray<WorkspaceView> | undefined => useAtomValue(allWorkspaceViewsAtom);

// Stable fallback for when there is no current workspace, so the hook's
// memoized selection always has a constant source atom.
const noCurrentWorkspaceAtom = atom<WorkspaceView | null>(null);

/**
 * The workspace the user is currently in — the panel's workspace when mounted
 * in a panel, otherwise the current route — or `null` when there is none (e.g.
 * an overlay on the home or settings screen). Named for its nullability and to
 * avoid shadowing the host's by-id `useWorkspace`, which has different
 * semantics.
 *
 * Pass a `selector` to subscribe to one field and re-render only when that
 * field changes (backed by jotai's `selectAtom`):
 *
 *     const branch = useCurrentWorkspace((w) => w?.branch ?? null);
 *
 * The selector should be pure over the workspace (no external closure state):
 * its identity may change between renders, but its logic must not.
 */
export function useCurrentWorkspace<T = WorkspaceView | null>(
  selector?: (workspace: WorkspaceView | null) => T,
  equalityFn?: (a: T, b: T) => boolean,
): T {
  // Resolve the active id: the panel's workspace if mounted in one (read
  // non-throwing, so overlays don't crash), else the current route.
  const panelContext = useContext(WorkspacePluginContext);
  const { workspaceID } = useParams<{ workspaceID?: string }>();
  const workspaceId = panelContext?.workspaceId ?? workspaceID ?? null;

  // selectAtom rebuilds its derived atom whenever the selector/equality
  // *identity* changes — which an inline selector does every render. Keep the
  // latest in refs and hand selectAtom stable wrappers, so a field selector
  // subscribes once and re-renders only when that field changes. The refs are
  // updated after commit (never during render) and read only when jotai later
  // invokes the selector/equality wrappers, so the latest values are in place.
  const selectorRef = useRef(selector);
  const equalityRef = useRef(equalityFn);
  useEffect(() => {
    selectorRef.current = selector;
    equalityRef.current = equalityFn;
  });

  const sourceAtom = useMemo(
    () => (workspaceId ? workspaceViewAtomFamily(workspaceId) : noCurrentWorkspaceAtom),
    [workspaceId],
  );
  const selectedAtom = useMemo(
    () =>
      selectAtom<WorkspaceView | null, T>(
        sourceAtom,
        // eslint-disable-next-line react-hooks/refs -- jotai invokes these wrappers when it evaluates the atom, not during render; the ref indirection is what keeps the wrappers' identity stable so selectAtom subscribes once.
        (workspace) => (selectorRef.current ? selectorRef.current(workspace) : (workspace as unknown as T)),
        // eslint-disable-next-line react-hooks/refs -- see above: read happens at atom-evaluation time, not during render.
        (a, b) => (equalityRef.current ? equalityRef.current(a, b) : Object.is(a, b)),
      ),
    [sourceAtom],
  );
  return useAtomValue(selectedAtom);
}

/**
 * Returns a function that navigates to a workspace by id — the host's own
 * workspace-open behavior: it opens (or converts the home tab into) the
 * workspace's tab and jumps to its most-recently-used agent. The blessed seam
 * for a plugin to send the user into a workspace (e.g. a home view opening the
 * workspace a ticket is being worked in), so the navigation stays consistent
 * with clicking a workspace in the host's own lists.
 */
export const useNavigateToWorkspace = (): ((workspaceId: string) => void) =>
  // navigateToWorkspaceById is already a stable callback, so hand it back as-is.
  useWorkspaceNavigation().navigateToWorkspaceById;

// One persisted atom per (plugin, key). atomFamily caches by the full storage
// key; getOnInit reads localStorage synchronously so the value is present on
// first render instead of flashing the default.
const pluginSettingAtomFamily = atomFamily((storageKey: string) =>
  atomWithStorage<string>(storageKey, "", undefined, { getOnInit: true }),
);

// The localStorage namespace for one of a plugin's settings. Shared by the
// single- and multi-key hooks so the key shape can't drift between them.
const settingStorageKey = (pluginId: string, key: string): string => `sculptor-plugin:${pluginId}:${key}`;

/**
 * A persisted string setting scoped to the calling plugin. Backed by
 * localStorage under a `sculptor-plugin:<id>:<key>` namespace and shared
 * reactively across the plugin's panel and its settings component.
 */
export const usePluginSetting = (key: string): [string, (value: string) => void] => {
  const { pluginId } = usePluginContext();
  return useAtom(pluginSettingAtomFamily(settingStorageKey(pluginId, key)));
};

/**
 * Read several of the calling plugin's persisted settings at once, reactively —
 * the multi-key companion to {@link usePluginSetting} for when the set of keys
 * is dynamic, so you can't call `usePluginSetting` once per key (e.g. one
 * per-workspace key, with the workspace list coming from `useWorkspaces`).
 * Returns a map from each requested key to its current value (the empty string
 * for an unset key) and re-renders when any of those keys changes — including a
 * write from another surface of the plugin, since both share the same per-key
 * atoms.
 */
export const usePluginSettings = (keys: ReadonlyArray<string>): ReadonlyMap<string, string> => {
  const { pluginId } = usePluginContext();
  // Encode the key set so the derived atom is rebuilt only when the set itself
  // changes — a fresh `keys` array every render would otherwise rebuild it each
  // time. Plugin keys are `<name>:<id>`-style and never contain a newline, so it
  // is a safe separator to split back out inside the atom.
  const encodedKeys = keys.join("\n");
  const mapAtom = useMemo(
    () =>
      atom((get): ReadonlyMap<string, string> => {
        const requestedKeys = encodedKeys === "" ? [] : encodedKeys.split("\n");
        return new Map(
          requestedKeys.map((key) => [key, get(pluginSettingAtomFamily(settingStorageKey(pluginId, key)))]),
        );
      }),
    [pluginId, encodedKeys],
  );
  return useAtomValue(mapAtom);
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
