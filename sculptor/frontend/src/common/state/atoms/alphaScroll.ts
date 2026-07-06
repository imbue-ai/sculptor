import type { PrimitiveAtom } from "jotai";
import { atom } from "jotai";
import { atomFamily } from "jotai/utils";

export type AlphaScrollPosition = {
  firstVisibleMessageId: string;
  pixelOffset: number;
  /** Signed distance from the viewport bottom to the content bottom (the
   *  virtualizer's paddingEnd excluded); negative when the viewport sits past
   *  the content, inside the tail padding. */
  distanceFromBottom: number;
};

export const alphaScrollPositionAtomFamily = atomFamily<string, PrimitiveAtom<AlphaScrollPosition | undefined>>(() =>
  atom<AlphaScrollPosition | undefined>(undefined),
);
