import { useSetAtom } from "jotai";
import { useEffect } from "react";

import { postAgentTerminalInput, TaskStatus } from "~/api";
import { chatActionsAtom } from "~/common/state/atoms/chatActions.ts";
import { terminalPromptRejectedToastAtom } from "~/common/state/atoms/toasts.ts";
import { useTaskAcceptsAutomatedPrompts, useTaskStatus } from "~/common/state/hooks/useTaskHelpers.ts";

/**
 * Terminal-panel counterpart of useChatData's chatActions registration: the
 * single seam that makes the prompt-driven features (Commit, Create PR,
 * custom actions) work for automated-prompt-capable terminal agents.
 *
 * When the agent's registration opted in (`acceptsAutomatedPrompts`),
 * `sendMessage` routes the prompt through the terminal-input endpoint so it
 * arrives as typed input; otherwise nothing is registered and every consumer
 * stays disabled by default. Consumers are untouched — the routing decision
 * lives entirely in which hook registered the actions.
 */
export const useTerminalChatActions = (taskId: string): void => {
  const doesAcceptAutomatedPrompts = useTaskAcceptsAutomatedPrompts(taskId);
  const status = useTaskStatus(taskId);
  const setChatActions = useSetAtom(chatActionsAtom);
  const setPromptRejectedToast = useSetAtom(terminalPromptRejectedToastAtom);

  useEffect(() => {
    if (!doesAcceptAutomatedPrompts) {
      // Plain terminals and non-opt-in registrations: leave the default
      // disabled state registered.
      return;
    }
    setChatActions((prev) => ({
      ...prev,
      // No editor exists for terminal agents — appendText/insertSkill stay
      // null and consumers already null-check them.
      sendMessage: async (message: string): Promise<void> => {
        try {
          await postAgentTerminalInput({ path: { agent_id: taskId }, body: { text: message, submit: true } });
        } catch {
          // The endpoint's authoritative guard fired: the program went busy
          // (or its hooks are silent) between the click and the write.
          // Surface it; do not retry.
          setPromptRejectedToast({ title: "Agent is busy", description: "Try again when it's at its prompt." });
        }
      },
    }));
  }, [setChatActions, setPromptRejectedToast, doesAcceptAutomatedPrompts, taskId]);

  // Track `isDisabled` separately (mirrors useChatData) so status flips don't
  // re-bind the send closure. READY can also mean "no signals yet" — the
  // endpoint 409s that case and the toast above covers it.
  useEffect(() => {
    if (!doesAcceptAutomatedPrompts) {
      return;
    }
    const isDisabled = !(status === TaskStatus.READY || status === TaskStatus.WAITING);
    setChatActions((prev) => ({ ...prev, isDisabled }));
  }, [setChatActions, doesAcceptAutomatedPrompts, status]);

  // On unmount, null the closures and flip isDisabled back to true — same
  // teardown as useChatData, so tab switches hand the atom over cleanly.
  useEffect(() => {
    return (): void => {
      setChatActions({ appendText: null, insertSkill: null, sendMessage: null, isDisabled: true });
    };
  }, [setChatActions]);
};
