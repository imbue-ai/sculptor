import type { Editor as TipTapEditor } from "@tiptap/react";
import { useAtomValue, useSetAtom } from "jotai";
import { type ReactElement, useEffect, useRef } from "react";

import { closeBtwPopupIfNotForAgentAtom, isBtwPopupOpenAtom } from "~/common/state/atoms/btwPopup.ts";
import type { InsertSkillArg } from "~/common/state/atoms/chatActions.ts";
import { useTaskSupportsChatInterface, useTaskWorkspaceId } from "~/common/state/hooks/useTaskHelpers.ts";
import { chatPanelMountedAtom } from "~/pages/workspace/atoms.ts";
import { lastFocusedChatAgentAtomFamily } from "~/pages/workspace/panels/workspaceAgentActions.ts";

import { AgentTerminalPanel } from "./AgentTerminalPanel.tsx";
import { BtwPopup } from "./BtwPopup.tsx";
import { AlphaChatInterface } from "./chat-alpha/AlphaChatInterface.tsx";
import { ChatTaskProvider } from "./chat-alpha/ChatTaskContext.tsx";
import styles from "./ChatPanelContent.module.scss";
import { useChatData } from "./useChatData.ts";

type ChatPanelContentProps = {
  // The task this panel renders. Supplied as a prop (not read from the route) so each
  // agent panel renders its OWN agent — one in center and another in right at once,
  // two streaming concurrently.
  taskId: string;
};

/**
 * The main-panel switch: terminal agents get a full-pane terminal in the
 * space the chat interface occupies for chat agents, driven by the
 * `supports_chat_interface` capability.
 *
 * The switch lives outside `ChatPanelInner` because `useChatData` must not
 * run for terminal agents — it registers `chatActionsAtom` closures, which
 * is exactly what keeps Commit / Create PR / custom actions disabled for
 * them (the load-bearing gate).
 */
export const ChatPanelContent = ({ taskId }: ChatPanelContentProps): ReactElement | null => {
  const isChatInterfaceSupported = useTaskSupportsChatInterface(taskId);

  if (isChatInterfaceSupported === false) {
    // Keyed by task id: a direct terminal->terminal tab switch must remount
    // the panel so each agent gets its own xterm instance. Without the key,
    // React reuses the component and the previous agent's scrollback stays
    // in the (single) xterm buffer when the WebSocket reconnects to the new
    // agent's PTY — leaking one tab's content into another.
    return <AgentTerminalPanel key={taskId} taskId={taskId} />;
  }

  // While capabilities are loading, render nothing rather than the chat —
  // mounting useChatData for a terminal agent would register chat actions,
  // and a chat→terminal swap flashes. This deliberately differs from
  // useCapabilityGate's `?? true` affordance default.
  if (isChatInterfaceSupported === undefined) {
    return null;
  }
  return <ChatPanelInner taskId={taskId} />;
};

const ChatPanelInner = ({ taskId }: ChatPanelContentProps): ReactElement => {
  // The chat data hook needs the task's workspace id; derive it from the task
  // rather than the route — the panel's agent can differ from the routed one
  // (any placed agent panel renders this component). The narrow field hook
  // keeps unrelated task churn (status, timestamps) from re-rendering the whole
  // chat surface.
  const workspaceID = useTaskWorkspaceId(taskId) ?? "";

  // Registration seams tying this panel's composer to the workspace-scoped
  // consumers: useChatData registers the chatActions append/insert closures
  // against these refs and ChatInput registers its TipTap editor, so
  // SkillsPanel / ActionsPanel inserts land in this panel's editor.
  const appendTextRef = useRef<((text: string) => void) | null>(null);
  const insertSkillRef = useRef<((skill: InsertSkillArg) => void) | null>(null);
  const editorRef = useRef<TipTapEditor | null>(null);
  const closeBtwPopupIfNotForAgent = useSetAtom(closeBtwPopupIfNotForAgentAtom);
  const isBtwPopupOpen = useAtomValue(isBtwPopupOpenAtom);
  const setChatPanelMounted = useSetAtom(chatPanelMountedAtom);
  const recordChatAgentFocus = useSetAtom(lastFocusedChatAgentAtomFamily(workspaceID));

  const chatData = useChatData({ taskID: taskId, workspaceID, appendTextRef, insertSkillRef });

  // /btw popups are scoped to the agent that opened them. Whenever the
  // active agent changes (tab switch, workspace switch, navigation), the
  // popup atom may still hold the previous agent's question/answer; close
  // it so it doesn't float above an unrelated chat pane.
  useEffect(() => {
    closeBtwPopupIfNotForAgent(taskId);
  }, [taskId, closeBtwPopupIfNotForAgent]);

  // Reactive signal for "is a chat panel currently rendered?" — read by the
  // command palette (via `chatPanelMountedAtom`) instead of poking the DOM.
  // Increment/decrement a shared counter so the signal stays correct when two
  // chat panels are mounted at once (e.g. one in the center section and one
  // moved to the right).
  useEffect(() => {
    setChatPanelMounted((count) => count + 1);
    return (): void => {
      setChatPanelMounted((count) => count - 1);
    };
  }, [setChatPanelMounted]);

  // Workspace-scoped actions (commit prompt, Notes/Skills insertion) target
  // the most-recently-focused chat, so any pointer-down or focus inside this
  // panel marks its agent as that target. Capture-phase handlers see events
  // that inner components swallow; the atom setter is equality-guarded, so
  // recording on every interaction stays cheap. The workspace id is briefly
  // "" while the task atom loads — skip recording rather than key a family
  // entry on a placeholder id.
  const handleChatInteraction = (): void => {
    if (workspaceID !== "") {
      recordChatAgentFocus(taskId);
    }
  };

  // Render the popup as a sibling of the chat interface so it lives at the
  // workspace-route scope (only mounted when the user is looking at a chat
  // pane). The popup itself is `position: fixed`, so where it lives in the
  // tree doesn't affect its on-screen anchor — viewport bottom-right.
  // Mount it only while the popup is open so close→reopen produces a fresh
  // component instance with no carry-over local state (e.g. drag position).
  //
  // ChatTaskProvider seeds the chat surface with this PANEL's agent identity;
  // every component underneath reads it from context rather than the route,
  // so a panel showing a non-route agent still targets its own agent.
  //
  // The focus-recording wrapper is `display: contents`: the chat surface
  // sizes itself against the panel container (height: 100%), so the wrapper
  // must not introduce a layout box of its own.
  return (
    <ChatTaskProvider workspaceId={workspaceID} taskId={taskId}>
      <div
        className={styles.focusRecorder}
        onFocusCapture={handleChatInteraction}
        onPointerDownCapture={handleChatInteraction}
      >
        <AlphaChatInterface
          {...chatData}
          appendTextRef={appendTextRef}
          insertSkillRef={insertSkillRef}
          editorRef={editorRef}
        />
        {isBtwPopupOpen && <BtwPopup />}
      </div>
    </ChatTaskProvider>
  );
};
