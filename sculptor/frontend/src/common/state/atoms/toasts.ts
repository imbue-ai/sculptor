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

export type InfoToastData = {
  title: string;
  description?: ReactNode;
};

// Surfaced when an @-mention chip click cannot be fulfilled (target is hidden
// from the file browser, lives outside the workspace, or no longer exists).
export const mentionChipUnreachableToastAtom = atom<InfoToastData | null>(null);
