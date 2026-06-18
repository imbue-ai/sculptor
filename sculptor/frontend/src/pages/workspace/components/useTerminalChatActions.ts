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
 * `sendMessage` (auto-send) and `appendText` (non-auto-send draft) both route
 * the prompt through the terminal-input endpoint, differing only in whether
 * the submit Enter is sent; otherwise nothing is registered and every consumer
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

    // Both prompt seams write through the same terminal-input endpoint and
    // differ only in whether the submit Enter is sent. `submit: true`
    // (auto-send actions, Commit, Create PR) types the prompt and submits it;
    // `submit: false` (non-auto-send "draft" actions) types it into the PTY
    // and leaves it unsubmitted for the user to edit/send — the terminal
    // counterpart of appendText populating a rich-chat composer.
    const writePrompt = async (text: string, submit: boolean): Promise<void> => {
      try {
        await postAgentTerminalInput({ path: { agent_id: taskId }, body: { text, submit } });
      } catch {
        // The endpoint's authoritative guard fired: the program went busy
        // (or its hooks are silent) between the click and the write.
        // Surface it; do not retry.
        setPromptRejectedToast({ title: "Agent is busy", description: "Try again when it's at its prompt." });
      }
    };
    setChatActions((prev) => ({
      ...prev,
      // No rich-text editor exists for terminal agents, so insertSkill stays
      // null (consumers already null-check it). appendText drafts the prompt
      // into the PTY without submitting (submit: false).
      appendText: (text: string): void => {
        void writePrompt(text, false);
      },
      sendMessage: (message: string): Promise<void> => writePrompt(message, true),
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
