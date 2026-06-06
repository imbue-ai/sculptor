import { Flex } from "@radix-ui/themes";
import type { Editor as TipTapEditor } from "@tiptap/react";
import type { ReactElement } from "react";
import { useRef } from "react";

import { AgentOverrideContext } from "~/common/NavigateUtils.ts";
import type { InsertSkillArg } from "~/common/state/atoms/chatActions.ts";
import { ChatPanelContent } from "~/pages/workspace/components/ChatPanelContent.tsx";

/**
 * An agent (task) rendered as a panel (REQ-AGENT-1). Each agent is its own
 * single-instance panel; the chat subtree is scoped to `agentId` via
 * AgentOverrideContext so every descendant that reads the active agent resolves
 * to this panel's agent rather than the URL's. Each panel owns its own chat
 * input refs, so side-by-side agents have independent inputs.
 */
export const AgentPanel = ({ agentId }: { agentId: string }): ReactElement => {
  const appendTextRef = useRef<((text: string) => void) | null>(null);
  const insertSkillRef = useRef<((skill: InsertSkillArg) => void) | null>(null);
  const editorRef = useRef<TipTapEditor | null>(null);

  return (
    <AgentOverrideContext.Provider value={agentId}>
      <Flex direction="column" height="100%" overflow="hidden">
        <ChatPanelContent appendTextRef={appendTextRef} insertSkillRef={insertSkillRef} editorRef={editorRef} />
      </Flex>
    </AgentOverrideContext.Provider>
  );
};
