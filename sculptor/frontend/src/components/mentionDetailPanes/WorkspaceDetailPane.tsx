import { useAtomValue } from "jotai";
import type { ReactElement } from "react";

import { workspaceDetailAtomFamily } from "~/common/state/atoms/mentionDetails";

import { TYPE_ICONS } from "../EntityMentionSuggestion";
import { MentionDetailPaneShell } from "./MentionDetailPaneShell";

type WorkspaceDetailPaneProps = {
  workspaceId: string;
  entityDisplayName: string;
};

const agentCountMeta = (count: number): string => {
  if (count === 0) return "No agents yet";
  if (count === 1) return "1 agent";
  return `${count} agents`;
};

/**
 * Detail pane for a `+[workspace:id|name]` chip. Reads the composite
 * `workspaceDetailAtomFamily` so a single subscription pulls the
 * workspace, parent project, and its non-deleted agents.
 */
export const WorkspaceDetailPane = ({ workspaceId, entityDisplayName }: WorkspaceDetailPaneProps): ReactElement => {
  const detail = useAtomValue(workspaceDetailAtomFamily(workspaceId));

  if (detail === null) {
    return (
      <MentionDetailPaneShell
        color="teal"
        icon={TYPE_ICONS.workspace}
        title={entityDisplayName}
        deleted
        meta="Workspace no longer exists"
      />
    );
  }

  const title = detail.workspace.description !== "" ? detail.workspace.description : entityDisplayName;

  return (
    <MentionDetailPaneShell
      color="teal"
      icon={TYPE_ICONS.workspace}
      title={title}
      badge={detail.project?.name}
      meta={agentCountMeta(detail.agentCount)}
    />
  );
};
