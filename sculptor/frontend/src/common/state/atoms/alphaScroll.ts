import type { PrimitiveAtom } from "jotai";
import { atom } from "jotai";
import { atomFamily } from "jotai/utils";

export type AlphaScrollPosition = {
  firstVisibleMessageId: string;
  pixelOffset: number;
  distanceFromBottom: number;
};

export const alphaScrollPositionAtomFamily = atomFamily<string, PrimitiveAtom<AlphaScrollPosition | undefined>>(() =>
  atom<AlphaScrollPosition | undefined>(undefined),
);
