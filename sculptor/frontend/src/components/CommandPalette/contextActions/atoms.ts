import { atom } from "jotai";

/**
 * Atoms for state shared by tab right-click menus and the command palette.
 *
 * The pre-existing tabs components (`WorkspaceTabs`, `AgentTabs`) used local
 * `useState` for "currently renaming this id" and "delete-confirmation
 * target." Lifting these to atoms lets context-action handlers invoked
 * from anywhere — including the command palette runtime — drive the same
 * UI flows the right-click menu drives.
 *
 * Both tab components subscribe to these atoms in place of their previous
 * local state.
 */

export const renamingWorkspaceIdAtom = atom<string | null>(null);

export const workspaceDeleteTargetAtom = atom<{ id: string; name: string } | null>(null);

export const renamingAgentIdAtom = atom<string | null>(null);

export const agentDeleteTargetAtom = atom<{ id: string; name: string } | null>(null);

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
