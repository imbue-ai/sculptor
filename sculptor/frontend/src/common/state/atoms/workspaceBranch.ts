import type { PrimitiveAtom } from "jotai";
import { atom } from "jotai";
import { atomFamily } from "jotai/utils";

import type { WorkspaceBranchInfo } from "../../../api";

export const workspaceBranchAtomFamily = atomFamily<string, PrimitiveAtom<WorkspaceBranchInfo | null>>(() =>
  atom<WorkspaceBranchInfo | null>(null),
);

export const updateWorkspaceBranchAtom = atom(
  null,
  (getAtom, setAtom, update: { workspaceId: string; branchInfo: WorkspaceBranchInfo | null }) => {
    const atomForWorkspace = workspaceBranchAtomFamily(update.workspaceId);
    setAtom(atomForWorkspace, update.branchInfo);
  },
);
