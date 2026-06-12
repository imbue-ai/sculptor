import type { PrimitiveAtom } from "jotai";
import { atom } from "jotai";
import { atomFamily } from "jotai/utils";

import type { CiBabysitterWorkspaceStateResponse } from "../../../api";
import { getCiBabysitterState, setCiBabysitterPaused } from "../../../api";

export const ciBabysitterStatusAtomFamily = atomFamily<
  string,
  PrimitiveAtom<CiBabysitterWorkspaceStateResponse | null>
>(() => atom<CiBabysitterWorkspaceStateResponse | null>(null));

// Increments on every fetch initiated by `fetchCiBabysitterStatusAtom`. A
// per-workspace tracker would be cleaner, but keeping a single counter is
// sufficient because the popover only fetches one workspace at a time;
// older in-flight responses with a stale counter are dropped before they
// can overwrite a newer fetch's data.
const ciBabysitterFetchSeqAtom = atom(0);

export const fetchCiBabysitterStatusAtom = atom(null, async (get, set, workspaceId: string) => {
  const seq = get(ciBabysitterFetchSeqAtom) + 1;
  set(ciBabysitterFetchSeqAtom, seq);
  const response = await getCiBabysitterState({ path: { workspace_id: workspaceId } });
  if (response.data && get(ciBabysitterFetchSeqAtom) === seq) {
    set(ciBabysitterStatusAtomFamily(workspaceId), response.data);
  }
});

export const setCiBabysitterPausedAtom = atom(
  null,
  async (_get, set, params: { workspaceId: string; paused: boolean }) => {
    const response = await setCiBabysitterPaused({
      path: { workspace_id: params.workspaceId },
      body: { paused: params.paused },
    });
    if (response.data) {
      set(ciBabysitterStatusAtomFamily(params.workspaceId), response.data);
    }
  },
);
