import type { PrimitiveAtom } from "jotai";
import { atom } from "jotai";
import { atomFamily } from "jotai/utils";

import type { WorkspaceSetupStatus } from "../../../api";
import { workspaceSetupOutputAtomFamily } from "./workspaceSetupOutput";

// We widen `startedAt` to allow `null` so we can seed a speculative "running"
// status at workspace-create time (before the backend has reported a real
// `started_at`). The SetupStatusCard already handles `startedAt === null`
// by hiding the elapsed timer.
export type SetupStatusSnapshot = Omit<WorkspaceSetupStatus, "startedAt" | "finishedAt"> & {
  startedAt?: number | null;
  finishedAt?: number | null;
};

export const workspaceSetupStatusAtomFamily = atomFamily<string, PrimitiveAtom<SetupStatusSnapshot | null>>(() =>
  atom<SetupStatusSnapshot | null>(null),
);

export const updateWorkspaceSetupStatusAtom = atom(
  null,
  (getAtom, setAtom, update: { workspaceId: string; status: SetupStatusSnapshot | null }) => {
    // When the run identity changes, clear the previous run's output buffer.
    // Otherwise a rerun whose new command produces no output (e.g. `false`)
    // would leave the previous run's text on screen — chunk events only
    // arrive when the new run actually emits bytes.
    const newRunId =
      update.status !== null && typeof update.status.runId === "string" && update.status.runId.length > 0
        ? update.status.runId
        : null;
    if (newRunId !== null) {
      const outputAtom = workspaceSetupOutputAtomFamily(update.workspaceId);
      const currentOutput = getAtom(outputAtom);
      if (currentOutput !== null && currentOutput.runId !== newRunId) {
        setAtom(outputAtom, null);
      }
    }
    setAtom(workspaceSetupStatusAtomFamily(update.workspaceId), update.status);
  },
);
