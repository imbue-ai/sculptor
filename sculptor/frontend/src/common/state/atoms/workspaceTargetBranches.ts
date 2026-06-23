import type { PrimitiveAtom } from "jotai";
import { atom } from "jotai";
import { atomFamily } from "jotai/utils";

import type { WorkspaceTargetBranchesInfo } from "../../../api";

export const workspaceTargetBranchesAtomFamily = atomFamily<string, PrimitiveAtom<WorkspaceTargetBranchesInfo | null>>(
  () => atom<WorkspaceTargetBranchesInfo | null>(null),
);

export const updateWorkspaceTargetBranchesAtom = atom(
  null,
  (getAtom, setAtom, update: { workspaceId: string; targetBranchesInfo: WorkspaceTargetBranchesInfo | null }) => {
    const atomForWorkspace = workspaceTargetBranchesAtomFamily(update.workspaceId);
    setAtom(atomForWorkspace, update.targetBranchesInfo);
  },
);
