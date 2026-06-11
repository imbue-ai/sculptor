import { atom } from "jotai";

import { WorkspaceInitializationStrategy } from "../../api";
import type { ToastContent } from "../Toast.tsx";

/**
 * The user's path into the modal — only "palette" gets the back-arrow
 * affordance and Esc-once-pops-back behavior; "keybinding" / "topbar" /
 * "auto" treat the modal as a destination, so Esc closes immediately.
 */
export type NewWorkspaceModalEntrySource = "palette" | "keybinding" | "topbar" | "auto";

export const newWorkspaceModalOpenAtom = atom<boolean>(false);

export const newWorkspaceModalEntrySourceAtom = atom<NewWorkspaceModalEntrySource>("keybinding");

// ── Draft form fields ──────────────────────────────────────────────────
//
// All fields persist across modal open/close within a session and are
// cleared together on successful workspace creation. The legacy
// `/ws/new/:draftId` URL carried this state via React Router; the modal
// keeps it in atoms instead so it survives mount/unmount.

export const draftWorkspaceNameAtom = atom<string>("");

export const draftSelectedProjectIdAtom = atom<string | null>(null);

export const draftUserSelectedBranchAtom = atom<string | null>(null);

/**
 * Initialization strategy. Defaults to WORKTREE — the default workspace
 * mode. CLONE and IN_PLACE are opt-in via their respective user-config
 * flags (see the modal component's mode selector).
 */
export const draftInitializationModeAtom = atom<WorkspaceInitializationStrategy>(
  WorkspaceInitializationStrategy.WORKTREE,
);

/**
 * Manual override for the auto-filled branch name. `null` means "use
 * the auto-fill"; any string means the user has taken over.
 */
export const draftBranchNameOverrideAtom = atom<string | null>(null);

export const draftInitialPromptAtom = atom<string>("");

/**
 * Resets every draft field to its default. Called on successful submit.
 */
export const resetDraftAtom = atom(null, (_get, set): void => {
  set(draftWorkspaceNameAtom, "");
  set(draftUserSelectedBranchAtom, null);
  set(draftBranchNameOverrideAtom, null);
  set(draftInitialPromptAtom, "");
  // Note: we intentionally leave `draftSelectedProjectIdAtom` and
  // `draftInitializationModeAtom` so the next open re-uses the user's
  // last choices (matches today's MRU-project default behavior).
});

/**
 * True after the first-load auto-open has fired this app boot. Stops
 * the auto-open effect from re-popping the modal if the user closes
 * it without creating a workspace and then navigates around.
 */
export const newWorkspaceModalAutoOpenedAtom = atom<boolean>(false);

/**
 * Transient toast for the modal (success / error). Lives in an atom — not
 * the form's local state — so a toast set right before the form unmounts
 * (e.g. "initial message failed" → close + navigate to the new agent) still
 * renders. The always-mounted modal shell owns the `<Toast>`; the inner form
 * only writes here.
 */
export const newWorkspaceToastAtom = atom<ToastContent | null>(null);

/**
 * True while a create is in flight. Shared between the inner form (which sets
 * it around the create pipeline and disables its controls) and the always-
 * mounted shell (which refuses to close the dialog mid-create so a stray Esc
 * or overlay click can't cancel the request). Kept as an atom rather than form
 * state because the shell — which owns the dialog's `onOpenChange` — needs to
 * read it even though the form owns the submit.
 */
export const newWorkspaceSubmittingAtom = atom<boolean>(false);
