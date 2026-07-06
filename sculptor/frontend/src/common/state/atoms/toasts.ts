import { atom } from "jotai";
import type { ReactNode } from "react";

import type { ToastType } from "../../../components/Toast.tsx";

export type ErrorToastData = {
  title: string;
  description: ReactNode;
  type: ToastType;
  action: {
    label: string;
    handleClick: () => void;
  } | null;
};

export const deleteErrorToastAtom = atom<ErrorToastData | null>(null);
export const workspaceDeleteErrorToastAtom = atom<ErrorToastData | null>(null);
export const workspaceOpenCloseErrorToastAtom = atom<ErrorToastData | null>(null);
// Surfaced when an inline workspace rename fails on the backend; the optimistic
// name is rolled back, so this is the only signal the write didn't stick.
export const workspaceRenameErrorToastAtom = atom<ErrorToastData | null>(null);

// Surfaced when creating an agent (from the add-panel `+` dropdown or Cmd+K) fails on
// the backend; otherwise the failure would only reach the console.
export const createAgentErrorToastAtom = atom<ErrorToastData | null>(null);

// Surfaced when the sidebar repo-group "+" direct-create fails on the backend.
// That flow has no form on screen to show an inline error, so without this the
// failure would only reach the console while a blank dialog pops open.
export const createWorkspaceErrorToastAtom = atom<ErrorToastData | null>(null);

export type InfoToastData = {
  title: string;
  description?: ReactNode;
};

// Surfaced when an @-mention chip click cannot be fulfilled (target is hidden
// from the file browser, lives outside the workspace, or no longer exists).
export const mentionChipUnreachableToastAtom = atom<InfoToastData | null>(null);

// Surfaced when the terminal-input endpoint rejects an automated prompt
// (409): the program went busy — or its hooks are silent — between the
// button click and the server-side write.
export const terminalPromptRejectedToastAtom = atom<InfoToastData | null>(null);

// Surfaced when the commit button's chat-route send fails (network/HTTP): the
// prompt never reached the agent, and the button fires its onCommit callback
// without awaiting the send, so this toast is the only signal it didn't land.
export const commitPromptSendFailedToastAtom = atom<InfoToastData | null>(null);
