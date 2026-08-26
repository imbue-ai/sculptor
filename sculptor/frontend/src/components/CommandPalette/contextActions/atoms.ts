import { atom } from "jotai";

import type { SubSectionId } from "~/components/sections/sectionTypes.ts";

/**
 * Atoms for state shared by right-click context menus and the command palette.
 * Holding "currently renaming this id" and "delete-confirmation target" in
 * atoms (rather than local component state) lets context-action handlers
 * invoked from anywhere — including the command palette runtime — drive the
 * same UI flows the right-click menu drives.
 *
 * Agent rename reaches the panel tab's inline edit through
 * `agentRenameTargetAtom`: the palette runtime activates the agent's panel and
 * sets this atom to the panel id, and the mounted tab in `SectionHeader` reacts
 * by entering its existing inline-rename mode.
 */

/** Read by the sidebar workspace rows to switch into inline-rename mode. */
export const renamingWorkspaceIdAtom = atom<string | null>(null);

/**
 * A rename handoff the sidebar row menus flush once their menu has closed. The
 * sidebar `beginRename` stashes the target workspace id here instead of writing
 * `renamingWorkspaceIdAtom` directly: writing it while the right-click context
 * menu or the row's "..." dropdown is still open would mount — and focus — the
 * inline rename input inside the menu's still-active focus scope, which yanks
 * focus back and the resulting blur cancels the rename. Each menu's
 * `onCloseAutoFocus` is the consumer: it suppresses the focus restore, clears
 * this atom, and writes `renamingWorkspaceIdAtom`, so the input only ever mounts
 * with nothing competing for focus. Mirrors `palettePendingRenameAtom` for the
 * sidebar menu surfaces; see the `use_close_auto_focus_for_focus_handoff`
 * review rule.
 */
export const pendingWorkspaceRenameIdAtom = atom<string | null>(null);

/**
 * A rename handoff the palette flushes once its dialog has closed. The palette
 * runtimes' `beginRename` stash the target here instead of writing the rename
 * atoms directly: writing them while the palette is open would mount — and
 * focus — the inline rename input inside the dialog's still-active focus trap,
 * which yanks focus back into the dialog and the resulting blur cancels the
 * rename. The palette's `onCloseAutoFocus` is the single consumer: it clears
 * this atom, suppresses the dialog's focus restore, and performs the deferred
 * write, so the input only ever mounts with nothing competing for focus.
 */
export const palettePendingRenameAtom = atom<
  { kind: "agent"; panelId: string } | { kind: "workspace"; workspaceId: string } | null
>(null);

/**
 * The agent PANEL id whose tab should be in inline-rename mode, set by the
 * command palette's agent `beginRename`. The matching tab in `SectionHeader`
 * derives its rename mode from this atom during render (no effect, no local
 * mirror) and clears it on commit/cancel alongside the tab's own rename flag.
 * Null when no rename is pending.
 */
export const agentRenameTargetAtom = atom<string | null>(null);

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
