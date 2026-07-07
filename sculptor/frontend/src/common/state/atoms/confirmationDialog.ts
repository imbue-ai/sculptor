import { atom } from "jotai";

import type { ConfirmationDialogContent } from "~/components/confirmationDialogContent.ts";

// The payload driving an app-level confirmation dialog: the rendered content
// (title/description/confirm label/tone) plus the action to run on confirm. A
// non-null value opens the dialog; confirming or dismissing writes null back.
//
// Behavior is captured here at raise-time — like a toast's action callback — so
// any surface can raise a one-off confirmation just by setting the atom, without
// a bespoke owner component to host the confirm logic. This suits confirmations
// whose action is available at the call site; flows whose action needs hooks and
// fires from non-React code (the workspace/agent/terminal deletes) keep their own
// target atoms and headless owners instead.
export type ConfirmationDialogData = ConfirmationDialogContent & {
  onConfirm: () => void;
};

export const confirmationDialogAtom = atom<ConfirmationDialogData | null>(null);
