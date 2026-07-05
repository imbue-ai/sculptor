import { useAtomValue } from "jotai";
import type { ReactElement } from "react";

import { agentDetailAtomFamily } from "~/common/state/atoms/mentionDetails";

import { TYPE_ICONS } from "../EntityMentionSuggestion";
import { MentionDetailPaneShell } from "./MentionDetailPaneShell";

type AgentDetailPaneProps = {
  agentId: string;
  entityDisplayName: string;
};

// Cap a goal-derived title so the hover card stays compact when the agent has
// no explicit title and we fall back to the first line of its goal.
const GOAL_TITLE_MAX_LENGTH = 60;

const fallbackTitle = (agent: { title: string | null; goal?: string | null } | null, fallback: string): string => {
  if (agent === null) return fallback;
  if (agent.title !== null && agent.title !== "") return agent.title;
  if (agent.goal != null && agent.goal !== "") {
    const firstLine = agent.goal.split("\n")[0].slice(0, GOAL_TITLE_MAX_LENGTH);
    return firstLine;
  }
  return fallback;
};

/**
 * Detail pane for a `+[agent:id|name]` chip. Reads the composite
 * `agentDetailAtomFamily` so a single subscription pulls the agent,
 * derived status, and parent workspace.
 *
 * When the composite is null (deleted / unknown agent) the shell
 * renders with gray styling and a "deleted" meta note so the user
 * still sees the display name they mentioned.
 */
export const AgentDetailPane = ({ agentId, entityDisplayName }: AgentDetailPaneProps): ReactElement => {
  const detail = useAtomValue(agentDetailAtomFamily(agentId));

  if (detail === null) {
    return (
      <MentionDetailPaneShell
        color="violet"
        icon={TYPE_ICONS.agent}
        title={entityDisplayName}
        deleted
        meta="Agent no longer exists"
      />
    );
  }

  const title = fallbackTitle(detail.agent, entityDisplayName);
  const body: Array<{ text: string; mono?: boolean }> = [];
  // The goal line is surfaced unless it was used as the title fallback.
  if (
    detail.agent.title !== null &&
    detail.agent.title !== "" &&
    detail.agent.goal != null &&
    detail.agent.goal !== ""
  ) {
    body.push({ text: detail.agent.goal.split("\n")[0] });
  }

  if (detail.workspace !== null && detail.workspace.description !== "") {
    body.push({ text: `in ${detail.workspace.description}` });
  }
  return (
    <MentionDetailPaneShell
      color="violet"
      icon={TYPE_ICONS.agent}
      title={title}
      body={body.length > 0 ? body : undefined}
    />
  );
};
