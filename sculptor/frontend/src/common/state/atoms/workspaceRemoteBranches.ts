import type { PrimitiveAtom } from "jotai";
import { atom } from "jotai";
import { atomFamily } from "jotai/utils";

import type { WorkspaceRemoteBranchesInfo } from "../../../api";

export const workspaceRemoteBranchesAtomFamily = atomFamily<string, PrimitiveAtom<WorkspaceRemoteBranchesInfo | null>>(
  () => atom<WorkspaceRemoteBranchesInfo | null>(null),
);

export const updateWorkspaceRemoteBranchesAtom = atom(
  null,
  (getAtom, setAtom, update: { workspaceId: string; remoteBranchesInfo: WorkspaceRemoteBranchesInfo | null }) => {
    const atomForWorkspace = workspaceRemoteBranchesAtomFamily(update.workspaceId);
    setAtom(atomForWorkspace, update.remoteBranchesInfo);
  },
);
