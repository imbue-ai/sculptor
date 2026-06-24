import { atom, useAtom, useAtomValue } from "jotai";
import { atomFamily, atomWithStorage, selectAtom } from "jotai/utils";
import { useContext, useEffect, useMemo, useRef } from "react";
import { useParams } from "react-router-dom";

import type { CodingAgentTaskView, Workspace } from "~/api";
import { prStatusAtomFamily } from "~/common/state/atoms/prStatus.ts";
import { tasksArrayAtom } from "~/common/state/atoms/tasks.ts";
import { workspaceBranchAtomFamily } from "~/common/state/atoms/workspaceBranch.ts";
import { workspaceAtomFamily, workspacesArrayAtom } from "~/common/state/atoms/workspaces.ts";

import { usePluginContext } from "../PluginContext.tsx";
import { useWorkspacePluginContext, WorkspacePluginContext } from "../WorkspaceContext.tsx";

/**
 * Every non-deleted workspace known to the host, or `undefined` until the
 * first batch has loaded. App-global: it reads a shared atom and needs no
 * workspace context, so it works in an overlay as well as a panel.
 */
export const useWorkspaces = (): ReadonlyArray<Workspace> | undefined => useAtomValue(workspacesArrayAtom);

/**
 * A curated, plugin-facing view of a single workspace: identity, label, and
 * live git branch. Deliberately a subset — not the host's full `Workspace`
 * model — so the plugin contract doesn't couple to backend internals.
 */
export type CurrentWorkspace = {
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

// One derived view atom per workspace id, composing the workspace model with
// its live branch (which the host keeps in a separate atom) into the curated
// CurrentWorkspace shape.
const currentWorkspaceViewAtomFamily = atomFamily((id: string) =>
  atom((get): CurrentWorkspace | null => {
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

// Stable fallback for when there is no current workspace, so the hook's
// memoized selection always has a constant source atom.
const noCurrentWorkspaceAtom = atom<CurrentWorkspace | null>(null);

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
export function useCurrentWorkspace<T = CurrentWorkspace | null>(
  selector?: (workspace: CurrentWorkspace | null) => T,
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
    () => (workspaceId ? currentWorkspaceViewAtomFamily(workspaceId) : noCurrentWorkspaceAtom),
    [workspaceId],
  );
  const selectedAtom = useMemo(
    () =>
      selectAtom<CurrentWorkspace | null, T>(
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
