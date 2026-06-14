import type { Editor as TipTapEditor } from "@tiptap/react";
import { useAtomValue, useSetAtom } from "jotai";
import { type ReactElement, useEffect } from "react";

import { useWorkspacePageParams } from "~/common/NavigateUtils.ts";
import { debugViewAtomFamily } from "~/common/state/atoms/alphaScroll.ts";
import { closeBtwPopupIfNotForAgentAtom, isBtwPopupOpenAtom } from "~/common/state/atoms/btwPopup.ts";
import type { InsertSkillArg } from "~/common/state/atoms/chatActions.ts";
import { chatPanelMountedAtom } from "~/components/panels/atoms.ts";

import { BtwPopup } from "./BtwPopup";
import { AlphaChatInterface } from "./chat-alpha/AlphaChatInterface.tsx";
import { DebugChatView } from "./chat-alpha/DebugChatView.tsx";
import { useChatData } from "./useChatData.ts";

type ChatPanelContentProps = {
  appendTextRef?: React.MutableRefObject<((text: string) => void) | null>;
  insertSkillRef?: React.MutableRefObject<((skill: InsertSkillArg) => void) | null>;
  editorRef?: React.MutableRefObject<TipTapEditor | null>;
  /** Mobile: suppress the built-in desktop input; the shell supplies its own. */
  hideChatInput?: boolean;
};

export const ChatPanelContent = ({
  appendTextRef,
  insertSkillRef,
  editorRef,
  hideChatInput,
}: ChatPanelContentProps): ReactElement => {
  const { workspaceID, agentID: taskID } = useWorkspacePageParams();
  const isDebugView = useAtomValue(debugViewAtomFamily(taskID ?? ""));
  const closeBtwPopupIfNotForAgent = useSetAtom(closeBtwPopupIfNotForAgentAtom);
  const isBtwPopupOpen = useAtomValue(isBtwPopupOpenAtom);
  const setChatPanelMounted = useSetAtom(chatPanelMountedAtom);

  const chatData = useChatData({ taskID: taskID ?? "", workspaceID, appendTextRef, insertSkillRef });

  // /btw popups are scoped to the agent that opened them. Whenever the
  // active agent changes (tab switch, workspace switch, navigation), the
  // popup atom may still hold the previous agent's question/answer; close
  // it so it doesn't float above an unrelated chat pane.
  useEffect(() => {
    closeBtwPopupIfNotForAgent(taskID ?? null);
  }, [taskID, closeBtwPopupIfNotForAgent]);

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
        hideChatInput={hideChatInput}
      />
      {isBtwPopupOpen && <BtwPopup />}
    </>
  );
};
