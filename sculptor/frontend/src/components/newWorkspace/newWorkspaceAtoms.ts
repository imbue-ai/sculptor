import type { Atom, PrimitiveAtom, WritableAtom } from "jotai";
import { atom } from "jotai";
import { atomWithStorage } from "jotai/utils";

import type { ModelOption, WorkspaceInitializationStrategy } from "~/api";
import type { StoredAgentType } from "~/common/state/atoms/agentTabs.ts";
import { hasEverHadWorkspacesAtom, workspacesArrayAtom } from "~/common/state/atoms/workspaces.ts";

/**
 * Open/close state of the new-workspace modal plus optional seeds for the form
 * it hosts. `presetProjectId` is set when the dialog is opened from a repo
 * group's "+" so the form lands on that repo. `initialTitle` / `initialPrompt`
 * / `initialBranchName` seed the form's title, prompt, and new-branch-name
 * fields: the home page's first-run auto-open uses `initialPrompt` to seed the
 * `/sculptor:help` onboarding prompt, and extensions use the full seed set (via
 * the SDK's `useOpenNewWorkspaceModal`) to open the dialog pre-filled.
 * `onWorkspaceCreated` fires after each successful create while the dialog
 * stays associated with this open request (including repeat creates in
 * keep-open mode). Transient — the modal is ephemeral, so this resets on
 * reload.
 */
export type NewWorkspaceModalState = {
  open: boolean;
  presetProjectId?: string;
  initialTitle?: string;
  initialPrompt?: string;
  initialBranchName?: string;
  onWorkspaceCreated?: (workspaceId: string) => void;
};

export const newWorkspaceModalAtom: PrimitiveAtom<NewWorkspaceModalState> = atom<NewWorkspaceModalState>({
  open: false,
});

/**
 * The form's in-progress entries, stashed whenever the form unmounts —
 * Escape, an overlay click, the X, and the Settings-routing CTAs all close
 * the dialog the same way — and seeding the next open, where the open
 * request's explicit seeds still win. A successful create clears it, so a
 * completed form never resurrects. Deliberately not persisted: a draft lives
 * for the session, keeping reloads fresh and prompt text off disk.
 */
export type NewWorkspaceDraft = {
  projectId: string | null;
  title: string;
  prompt: string;
  branchNameOverride: string | null;
  mode: WorkspaceInitializationStrategy;
  sourceBranch: string | undefined;
  agentTypeValue: StoredAgentType;
  piSelectionOverride: ModelOption | undefined;
};

export const newWorkspaceDraftAtom: PrimitiveAtom<NewWorkspaceDraft | undefined> = atom<NewWorkspaceDraft | undefined>(
  undefined,
);

/**
 * The "keep open" switch: when on, Create keeps the dialog open for rapid
 * multi-create — the form resets its title/prompt/branch name back to their
 * seeds (blank fields and a re-rolled branch when the dialog was opened
 * unseeded), but retains the repo + agent type. Persisted so the preference
 * survives reloads.
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
 * Gates the home page's first-run auto-open of the new-workspace dialog:
 * true only while the loaded workspace list is empty AND no workspace has
 * ever existed this session. `false` while the list is still loading
 * (`undefined`) so the dialog never flashes on a boot that turns out to have
 * workspaces — the offer waits for the stream's first snapshot. Deleting the
 * last workspace keeps it false (`hasEverHadWorkspacesAtom` has latched):
 * the offer is an onboarding affordance, not an empty-list reflex.
 */
export const shouldOfferFirstRunWorkspaceAtom: Atom<boolean> = atom<boolean>((get) => {
  const workspaces = get(workspacesArrayAtom);
  if (workspaces === undefined) {
    return false;
  }
  return workspaces.length === 0 && !get(hasEverHadWorkspacesAtom);
});
