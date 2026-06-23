import type { PrimitiveAtom } from "jotai";
import { atom } from "jotai";
import { atomFamily } from "jotai/utils";

import type { PrStatusInfo } from "../../../api";

export const prStatusAtomFamily = atomFamily<string, PrimitiveAtom<PrStatusInfo | null>>(() =>
  atom<PrStatusInfo | null>(null),
);

export const updatePrStatusAtom = atom(
  null,
  (get, set, update: { workspaceId: string; prStatus: PrStatusInfo | null }) => {
    const atomForWorkspace = prStatusAtomFamily(update.workspaceId);
    set(atomForWorkspace, update.prStatus);
  },
);
