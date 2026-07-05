// The agent panel: a thin, shell-agnostic wrapper around the existing chat surface,
// parameterized by the task id the registry binds per agent:<taskId> panel. It reads
// no layout, split, or route state so the same
// component renders identically in the center or right section, and two instances with
// different task ids stream independently. All task data still comes from
// the existing data atoms via ChatPanelContent.

import type { ReactElement } from "react";

import { ChatPanelContent } from "../chatAlpha/ChatPanelContent.tsx";

export const AgentPanel = ({ taskId }: { taskId: string }): ReactElement => <ChatPanelContent taskId={taskId} />;
