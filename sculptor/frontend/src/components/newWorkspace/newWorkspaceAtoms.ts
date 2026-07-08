import type { Atom, PrimitiveAtom, WritableAtom } from "jotai";
import { atom } from "jotai";
import { atomWithStorage } from "jotai/utils";

import type { WorkspaceInitializationStrategy } from "~/api";
import type { StoredAgentType } from "~/common/state/atoms/agentTabs.ts";
import { workspacesArrayAtom } from "~/common/state/atoms/workspaces.ts";

/**
 * Open/close state of the new-workspace modal plus optional seeds for the form
 * it hosts. `presetProjectId` is set when the dialog is opened from a repo
 * group's "+" so the form lands on that repo. This atom is also the seam
 * plugins use (via the SDK's `useOpenNewWorkspaceModal`) to open the dialog
 * pre-filled: `initialTitle` / `initialPrompt` seed the form's title and
 * prompt fields, and `onWorkspaceCreated` fires after each successful create
 * while the dialog stays associated with this open request (including repeat
 * creates in keep-open mode). Transient — the modal is ephemeral, so this
 * resets on reload.
 */
export type NewWorkspaceModalState = {
  open: boolean;
  presetProjectId?: string;
  initialTitle?: string;
  initialPrompt?: string;
  onWorkspaceCreated?: (workspaceId: string) => void;
};

export const newWorkspaceModalAtom: PrimitiveAtom<NewWorkspaceModalState> = atom<NewWorkspaceModalState>({
  open: false,
});

/**
 * The "keep open" switch: when on, Create keeps the dialog open
 * for rapid multi-create — the form resets its title/prompt/branch but retains
 * the repo + agent type. Persisted so the preference survives reloads.
 */
export const keepNewWorkspaceModalOpenAtom: WritableAtom<boolean, [boolean], void> = atomWithStorage<boolean>(
  "sculptor-keep-new-workspace-modal-open",
  false,
  undefined,
  { getOnInit: true },
);

/**
 * The settings of the last successful create. Seeds the modal's defaults and
 * powers the sidebar "+" direct-create. Persisted; extends today's MRU
 * project + last-used agent type into the full set the direct-create reuses.
 *
 * `undefined` means "no successful create yet" — consumers fall back to their
 * own defaults (the MRU project, the last-used agent type, worktree mode).
 */
export type WorkspaceCreationSettings = {
  projectId: string;
  sourceBranch?: string;
  agentType: StoredAgentType;
  initStrategy: WorkspaceInitializationStrategy;
};

export const lastWorkspaceCreationSettingsAtom: WritableAtom<
  WorkspaceCreationSettings | undefined,
  [WorkspaceCreationSettings | undefined],
  void
> = atomWithStorage<WorkspaceCreationSettings | undefined>(
  "sculptor-last-workspace-creation-settings",
  undefined,
  undefined,
  { getOnInit: true },
);

/**
 * Derived over the live workspace list; gates the empty first-run page
 * and the sidebar empty-workspace special case. `false` while the
 * list is still loading (`undefined`) so the empty state never flashes before
 * the first snapshot arrives.
 */
export const isWorkspaceListEmptyAtom: Atom<boolean> = atom<boolean>((get) => {
  const workspaces = get(workspacesArrayAtom);
  if (workspaces === undefined) {
    return false;
  }
  return workspaces.length === 0;
});

/**
 * True in the empty first-run state, where navigation is deliberately pared
 * back to just the inline form + Settings. The global keyboard
 * shortcuts hook and the command palette's open path read this and no-op while
 * it's set, so Cmd+K and the rest of the shortcuts stay off until the first
 * workspace exists. Kept as a separate, intent-named atom so the
 * shortcut-gating contract is explicit and can diverge from the empty-page
 * render condition — and it does diverge on load: unlike
 * `isWorkspaceListEmptyAtom` (false while the list is still loading, so the
 * empty page never flashes), shortcuts stay DISABLED until the first snapshot
 * arrives. Otherwise a shortcut fired during the load window of a
 * zero-workspace boot (e.g. Cmd/Meta+T) could set `newWorkspaceModalAtom`
 * open right before the first-run swap unmounts the modal's host, leaving a
 * stale open request that pops the dialog over the first created workspace.
 */
export const areGlobalShortcutsDisabledAtom: Atom<boolean> = atom<boolean>((get) => {
  const workspaces = get(workspacesArrayAtom);
  return workspaces === undefined || workspaces.length === 0;
});
