// The agent panel: a thin, shell-agnostic wrapper around the existing chat surface,
// parameterized by the task id the registry binds per agent:<taskId> panel. It reads
// no layout, split, or route state (component_hierarchy.md → principle 2) so the same
// component renders identically in the center or right section, and two instances with
// different task ids stream independently (AGENT-03/05). All task data still comes from
// the existing data atoms via ChatPanelContent.

import type { ReactElement } from "react";

import { registerAgentPanelComponent } from "~/components/sections/registry/dynamicPanels.tsx";

import { ChatPanelContent } from "../components/ChatPanelContent.tsx";

export const AgentPanel = ({ taskId }: { taskId: string }): ReactElement => <ChatPanelContent taskId={taskId} />;

// Register at module load as the base the dynamicPanels cache binds per agent id.
registerAgentPanelComponent(AgentPanel);
