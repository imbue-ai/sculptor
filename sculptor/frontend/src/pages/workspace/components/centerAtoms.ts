import { atom } from "jotai";
import { atomFamily } from "jotai/utils";

// The agent (task) shown in the Center's SECOND chat pane when the chat is
// split. `null` means not split. Per-workspace, non-persisted: a chat split is
// an ephemeral comparison view that resets on reload (REQ-CHAT-1/2).
//
// The Center is a 2-pane maximum: pane A is always a chat, pane B is EITHER the
// diff viewer OR a second chat — mutually exclusive (REQ-CENTER-3). The two are
// kept exclusive by `CenterPanes`: opening a file clears the second chat, and
// opening a split closes the diff.
export const secondChatAgentIdAtomFamily = atomFamily((_workspaceId: string) => atom<string | null>(null));
