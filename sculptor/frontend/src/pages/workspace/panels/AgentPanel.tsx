// The agent panel: a thin, shell-agnostic wrapper around the existing chat surface,
// parameterized by the agent id the registry binds per agent:<agentId> panel. It reads
// no layout, split, or route state so the same
// component renders identically in the center or right section, and two instances with
// different agent ids stream independently. All agent data still comes from
// the existing data atoms via ChatPanelContent.

import type { ReactElement } from "react";

import { ChatPanelContent } from "../chat/ChatPanelContent.tsx";

export const AgentPanel = ({ agentId }: { agentId: string }): ReactElement => <ChatPanelContent agentId={agentId} />;
