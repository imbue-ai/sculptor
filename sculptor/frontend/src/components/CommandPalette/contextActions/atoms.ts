import { atom } from "jotai";

import type { SubSectionId } from "~/pages/workspace/layout/types/section.ts";

/**
 * Atoms for state shared by right-click context menus and the command palette.
 * Holding "currently renaming this id" and "delete-confirmation target" in
 * atoms (rather than local component state) lets context-action handlers
 * invoked from anywhere — including the command palette runtime — drive the
 * same UI flows the right-click menu drives.
 *
 * Agent rename has no atom here on purpose: it's the panel tab's inline edit,
 * driven by local state in `SectionHeader`, and isn't palette-triggerable.
 */

/** Read by the sidebar workspace rows to switch into inline-rename mode. */
export const renamingWorkspaceIdAtom = atom<string | null>(null);

export const workspaceDeleteTargetAtom = atom<{ id: string; name: string } | null>(null);

export const agentDeleteTargetAtom = atom<{ id: string; name: string } | null>(null);

/**
 * The terminal pending a close-confirmation, set when a terminal tab's close
 * button is hit. Carries everything the confirm handler needs to tear
 * the terminal down without a separate lookup: the panel id (to unplace from the
 * layout), the workspace id + backend index (to kill the shell via
 * closeWorkspaceTerminal), the persisted tab id (to drop from
 * terminalTabStateAtom), and the display name (for the dialog copy). Null when no
 * confirmation is open.
 */
export const terminalCloseTargetAtom = atom<{
  panelId: string;
  workspaceId: string;
  index: number;
  tabId: string;
  name: string;
} | null>(null);

/**
 * The workspace whose context-action sub-page is currently shown in the
 * command palette. Set by the workspace picker page-opener and read by
 * the dynamic provider for the `workspace.actions` sub-page. Cleared on
 * palette close.
 */
export const workspaceActionsTargetAtom = atom<string | null>(null);

/**
 * The agent whose context-action sub-page is currently shown in the
 * command palette. Stores both ids so the perform handlers can navigate /
 * delete / mark-unread without doing a separate workspace lookup.
 */
export const agentActionsTargetAtom = atom<{ workspaceId: string; agentId: string } | null>(null);

/**
 * The destination sub-section chosen on the Cmd+K "Add panel" location page,
 * read by the `addpanel.panels` provider to list and place panels for that
 * location. Cleared on palette close.
 */
export const addPanelTargetSubSectionAtom = atom<SubSectionId | null>(null);
