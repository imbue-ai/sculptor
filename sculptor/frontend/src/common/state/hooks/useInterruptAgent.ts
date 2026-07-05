import { useAtomValue, useStore } from "jotai";
import { useCallback, useState } from "react";

import { interruptWorkspaceAgent } from "../../../api";
import { type ToastContent, ToastType } from "../../../components/Toast.tsx";
import { isInterruptingAtomFamily } from "../atoms/interruptState.ts";

type UseInterruptAgentResult = {
  isInterrupting: boolean;
  interrupt: () => Promise<void>;
  toast: ToastContent | null;
  setToast: (toast: ToastContent | null) => void;
};

// Single source of truth for "stop the agent". Every surface that exposes a
// stop affordance (the Stop button on ThinkingIndicator/StatusPill, the Esc
// keybinding in ChatInput, the queued-message bar's interrupt-and-send) calls
// this hook so the gate, API call, and toast wording stay aligned.
//
// `isInterrupting` reads from a shared per-task atom so all surfaces reflect
// the same in-flight state at the same time. The setter goes through the
// store directly (not the React-aware setter) so rapid presses see the latest
// value synchronously without waiting for React to re-render.
//
// Toast state is per-hook-instance: feedback appears next to whichever
// surface initiated the action.
export const useInterruptAgent = (
  workspaceID: string | undefined,
  taskID: string | undefined,
): UseInterruptAgentResult => {
  const store = useStore();
  const isInterrupting = useAtomValue(isInterruptingAtomFamily(taskID ?? ""));
  const [toast, setToast] = useState<ToastContent | null>(null);

  const interrupt = useCallback(async (): Promise<void> => {
    if (!taskID || !workspaceID) return;
    const interruptingAtom = isInterruptingAtomFamily(taskID);
    if (store.get(interruptingAtom)) return;
    store.set(interruptingAtom, true);
    try {
      await interruptWorkspaceAgent({ path: { workspace_id: workspaceID, agent_id: taskID } });
      setToast({ title: "Agent stopped successfully", type: ToastType.SUCCESS });
    } catch (error) {
      console.error("Failed to interrupt agent:", error);
      setToast({ title: "Failed to stop agent", type: ToastType.ERROR });
    } finally {
      store.set(interruptingAtom, false);
    }
  }, [store, workspaceID, taskID]);

  return { isInterrupting, interrupt, toast, setToast };
};
