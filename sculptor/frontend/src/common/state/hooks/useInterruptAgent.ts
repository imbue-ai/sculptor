import { useAtomValue, useStore } from "jotai";
import { useCallback, useState } from "react";

import { type ToastContent, ToastType } from "~/common/state/atoms/toasts.ts";

import { interruptWorkspaceAgent } from "../../../api";
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
// `isInterrupting` reads from a shared per-agent atom so all surfaces reflect
// the same in-flight state at the same time. The setter goes through the
// store directly (not the React-aware setter) so rapid presses see the latest
// value synchronously without waiting for React to re-render.
//
// Toast state is per-hook-instance: feedback appears next to whichever
// surface initiated the action.
export const useInterruptAgent = (
  workspaceID: string | undefined,
  agentId: string | undefined,
): UseInterruptAgentResult => {
  const store = useStore();
  const isInterrupting = useAtomValue(isInterruptingAtomFamily(agentId ?? ""));
  const [toast, setToast] = useState<ToastContent | null>(null);

  const interrupt = useCallback(async (): Promise<void> => {
    if (!agentId || !workspaceID) return;
    const interruptingAtom = isInterruptingAtomFamily(agentId);
    if (store.get(interruptingAtom)) return;
    store.set(interruptingAtom, true);
    try {
      await interruptWorkspaceAgent({ path: { workspace_id: workspaceID, agent_id: agentId } });
      setToast({ title: "Agent stopped successfully", type: ToastType.SUCCESS });
    } catch (error) {
      console.error("Failed to interrupt agent:", error);
      setToast({ title: "Failed to stop agent", type: ToastType.ERROR });
    } finally {
      store.set(interruptingAtom, false);
    }
  }, [store, workspaceID, agentId]);

  return { isInterrupting, interrupt, toast, setToast };
};
