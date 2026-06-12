import { atomWithStorage } from "jotai/utils";

export const collapsedGroupsAtom = atomWithStorage<Record<string, boolean>>("sculptor-collapsed-action-groups", {});
