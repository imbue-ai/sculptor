import { useAtomValue } from "jotai";
import type { ReactElement } from "react";

import { agentDetailAtomFamily } from "~/common/state/atoms/mentionDetails";

import { TYPE_ICONS } from "../EntityMentionSuggestion";
import { MentionDetailPaneShell } from "./MentionDetailPaneShell";

type AgentDetailPaneProps = {
  agentId: string;
  entityDisplayName: string;
};

// Cap a goal-derived title so the hover card stays compact when the task has
// no explicit title and we fall back to the first line of its goal.
const GOAL_TITLE_MAX_LENGTH = 60;

const fallbackTitle = (task: { title: string | null; goal?: string | null } | null, fallback: string): string => {
  if (task === null) return fallback;
  if (task.title !== null && task.title !== "") return task.title;
  if (task.goal != null && task.goal !== "") {
    const firstLine = task.goal.split("\n")[0].slice(0, GOAL_TITLE_MAX_LENGTH);
    return firstLine;
  }
  return fallback;
};

/**
 * Detail pane for a `+[agent:id|name]` chip. Reads the composite
 * `agentDetailAtomFamily` so a single subscription pulls the task,
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

  const title = fallbackTitle(detail.task, entityDisplayName);
  const body: Array<{ text: string; mono?: boolean }> = [];
  // The goal line is surfaced unless it was used as the title fallback.
  if (detail.task.title !== null && detail.task.title !== "" && detail.task.goal != null && detail.task.goal !== "") {
    body.push({ text: detail.task.goal.split("\n")[0] });
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
