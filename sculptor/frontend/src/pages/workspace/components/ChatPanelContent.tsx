import type { Editor as TipTapEditor } from "@tiptap/react";
import { useAtomValue, useSetAtom } from "jotai";
import { type ReactElement, useEffect } from "react";

import { debugViewAtomFamily } from "~/common/state/atoms/alphaScroll.ts";
import { closeBtwPopupIfNotForAgentAtom, isBtwPopupOpenAtom } from "~/common/state/atoms/btwPopup.ts";
import type { InsertSkillArg } from "~/common/state/atoms/chatActions.ts";
import { taskAtomFamily } from "~/common/state/atoms/tasks.ts";
import { useTaskSupportsChatInterface } from "~/common/state/hooks/useTaskHelpers.ts";
import { chatPanelMountedAtom } from "~/components/panels/atoms.ts";

import { AgentTerminalPanel } from "./AgentTerminalPanel.tsx";
import { BtwPopup } from "./BtwPopup.tsx";
import { AlphaChatInterface } from "./chat-alpha/AlphaChatInterface.tsx";
import { DebugChatView } from "./chat-alpha/DebugChatView.tsx";
import { useChatData } from "./useChatData.ts";

type ChatPanelContentProps = {
  // The task this panel renders. Supplied as a prop (not read from the route) so each
  // agent panel renders its OWN agent — one in center and another in right at once
  // (AGENT-03), two streaming concurrently (AGENT-05).
  taskId: string;
  appendTextRef?: React.MutableRefObject<((text: string) => void) | null>;
  insertSkillRef?: React.MutableRefObject<((skill: InsertSkillArg) => void) | null>;
  editorRef?: React.MutableRefObject<TipTapEditor | null>;
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
export const ChatPanelContent = ({
  taskId,
  appendTextRef,
  insertSkillRef,
  editorRef,
}: ChatPanelContentProps): ReactElement | null => {
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
  return (
    <ChatPanelInner
      taskId={taskId}
      appendTextRef={appendTextRef}
      insertSkillRef={insertSkillRef}
      editorRef={editorRef}
    />
  );
};

const ChatPanelInner = ({ taskId, appendTextRef, insertSkillRef, editorRef }: ChatPanelContentProps): ReactElement => {
  // The chat data hook needs the task's workspace id; derive it from the task atom
  // rather than the route so the panel stays shell-agnostic (principle 2).
  const workspaceID = useAtomValue(taskAtomFamily(taskId))?.workspaceId ?? "";
  const isDebugView = useAtomValue(debugViewAtomFamily(taskId));
  const closeBtwPopupIfNotForAgent = useSetAtom(closeBtwPopupIfNotForAgentAtom);
  const isBtwPopupOpen = useAtomValue(isBtwPopupOpenAtom);
  const setChatPanelMounted = useSetAtom(chatPanelMountedAtom);

  const chatData = useChatData({ taskID: taskId, workspaceID, appendTextRef, insertSkillRef });

  // /btw popups are scoped to the agent that opened them. Whenever the
  // active agent changes (tab switch, workspace switch, navigation), the
  // popup atom may still hold the previous agent's question/answer; close
  // it so it doesn't float above an unrelated chat pane.
  useEffect(() => {
    closeBtwPopupIfNotForAgent(taskId);
  }, [taskId, closeBtwPopupIfNotForAgent]);

  // Reactive signal for "is the chat panel currently rendered?" — read by the
  // command palette (via `chatPanelMountedAtom`) instead of poking the DOM.
  // The debug view replaces the chat panel and so doesn't count.
  const isChatPanelRendered = !isDebugView;
  useEffect(() => {
    if (!isChatPanelRendered) return;
    setChatPanelMounted(true);
    return (): void => {
      setChatPanelMounted(false);
    };
  }, [isChatPanelRendered, setChatPanelMounted]);

  if (isDebugView) {
    return <DebugChatView messages={chatData.chatMessages} />;
  }

  // Render the popup as a sibling of the chat interface so it lives at the
  // workspace-route scope (only mounted when the user is looking at a chat
  // pane). The popup itself is `position: fixed`, so where it lives in the
  // tree doesn't affect its on-screen anchor — viewport bottom-right.
  // Mount it only while the popup is open so close→reopen produces a fresh
  // component instance with no carry-over local state (e.g. drag position).
  return (
    <>
      <AlphaChatInterface
        {...chatData}
        appendTextRef={appendTextRef}
        insertSkillRef={insertSkillRef}
        editorRef={editorRef}
      />
      {isBtwPopupOpen && <BtwPopup />}
    </>
  );
};
