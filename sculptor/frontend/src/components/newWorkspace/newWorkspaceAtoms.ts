import type { Atom, PrimitiveAtom, WritableAtom } from "jotai";
import { atom } from "jotai";
import { atomWithStorage } from "jotai/utils";

import type { WorkspaceInitializationStrategy } from "~/api";
import type { StoredAgentType } from "~/common/state/atoms/agentTabs.ts";
import { workspacesArrayAtom } from "~/common/state/atoms/workspaces.ts";

/**
 * Open/close state of the new-workspace modal plus the optional repo it should
 * pre-select. `presetProjectId` is set when the dialog is opened from a repo
 * group's "+" so the form lands on that repo. Transient — the modal is
 * ephemeral, so this resets on reload.
 */
export type NewWorkspaceModalState = {
  open: boolean;
  presetProjectId?: string;
};

export const newWorkspaceModalAtom: PrimitiveAtom<NewWorkspaceModalState> = atom<NewWorkspaceModalState>({
  open: false,
});

/**
 * The "keep open" switch (Decision B8): when on, Create keeps the dialog open
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
 * powers the sidebar "+" direct-create (WSC-01). Persisted; extends today's MRU
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
 * (FIRST-01) and the sidebar empty-workspace special case. `false` while the
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
 * back to just the inline form + Settings (FIRST-03). The global keyboard
 * shortcuts hook and the command palette's open path read this and no-op while
 * it's set, so Cmd+K and the rest of the shortcuts stay off until the first
 * workspace exists. Tracks `isWorkspaceListEmptyAtom` exactly today; kept as a
 * separate, intent-named atom so the shortcut-gating contract is explicit and
 * can diverge later (e.g. allow more shortcuts) without touching the
 * empty-page render condition.
 */
export const areGlobalShortcutsDisabledAtom: Atom<boolean> = atom<boolean>((get) => get(isWorkspaceListEmptyAtom));
