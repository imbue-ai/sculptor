import type { PrimitiveAtom } from "jotai";
import { atom } from "jotai";
import { atomFamily } from "jotai/utils";

export type ChatScrollPosition = {
  firstVisibleMessageId: string;
  pixelOffset: number;
  /** Signed distance from the viewport bottom to the content bottom (the
   *  virtualizer's paddingEnd excluded); negative when the viewport sits past
   *  the content, inside the tail padding. */
  distanceFromBottom: number;
};

export const chatScrollPositionAtomFamily = atomFamily<string, PrimitiveAtom<ChatScrollPosition | undefined>>(() =>
  atom<ChatScrollPosition | undefined>(undefined),
);
