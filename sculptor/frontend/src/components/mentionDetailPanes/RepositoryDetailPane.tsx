import { useAtomValue } from "jotai";
import type { ReactElement } from "react";

import { repositoryDetailAtomFamily } from "~/common/state/atoms/mentionDetails";

import { TYPE_ICONS } from "../EntityMentionSuggestion";
import { MentionDetailPaneShell } from "./MentionDetailPaneShell";

type RepositoryDetailPaneProps = {
  projectId: string;
  entityDisplayName: string;
};

const workspaceCountMeta = (count: number): string => {
  if (count === 0) return "No workspaces yet";
  if (count === 1) return "1 workspace";
  return `${count} workspaces`;
};

/**
 * Detail pane for a `+[repository:id|name]` chip. Reads the composite
 * `repositoryDetailAtomFamily` so a single subscription pulls the
 * project and the workspaces attached to it.
 */
export const RepositoryDetailPane = ({ projectId, entityDisplayName }: RepositoryDetailPaneProps): ReactElement => {
  const detail = useAtomValue(repositoryDetailAtomFamily(projectId));

  if (detail === null) {
    return (
      <MentionDetailPaneShell
        color="amber"
        icon={TYPE_ICONS.repository}
        title={entityDisplayName}
        deleted
        meta="Repository no longer exists"
      />
    );
  }

  const gitUrl = detail.project.userGitRepoUrl ?? "";
  // `detail.workspaces` is already capped at DETAIL_PANE_PREVIEW_LIMIT in
  // the composite atom, so no slice is needed here.
  const body = detail.workspaces.map((workspace) => ({
    text: workspace.description !== "" ? workspace.description : "Untitled workspace",
    key: workspace.objectId,
  }));
  const bodyRows = gitUrl !== "" ? [{ text: gitUrl, mono: true, key: "git-url" }, ...body] : body;

  return (
    <MentionDetailPaneShell
      color="amber"
      icon={TYPE_ICONS.repository}
      title={detail.project.name}
      body={bodyRows.length > 0 ? bodyRows : undefined}
      meta={workspaceCountMeta(detail.workspaceCount)}
    />
  );
};
