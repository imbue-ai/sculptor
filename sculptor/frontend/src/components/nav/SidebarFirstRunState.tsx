// The sidebar repo area in the empty first-run state (no workspaces yet). With no
// repos at all it offers a single "Add a repo" button; with repos but no workspaces
// it lists each repo header followed by a "No workspaces yet" hint. Reuses the
// repo-group styles so the bare headers render exactly like populated groups.

import { Text } from "@radix-ui/themes";
import { FolderPlus } from "lucide-react";
import type { ReactElement } from "react";

import type { Project } from "~/api";
import { ElementIds } from "~/api";

import { NavItem } from "./NavItem.tsx";
import styles from "./SidebarRepoGroup.module.scss";

type SidebarFirstRunStateProps = {
  projects: ReadonlyArray<Project>;
  onAddRepo: () => void;
};

export const SidebarFirstRunState = ({ projects, onAddRepo }: SidebarFirstRunStateProps): ReactElement => {
  if (projects.length === 0) {
    return (
      <NavItem icon={FolderPlus} label="Add a repo" onClick={onAddRepo} testId={ElementIds.SIDEBAR_ADD_REPO_BUTTON} />
    );
  }
  return (
    <>
      {projects.map((project) => (
        <div key={project.objectId} className={styles.repoGroup}>
          <div className={styles.repoHeader}>
            <span className={styles.repoHeaderButton}>
              <Text className={styles.repoName} truncate>
                {project.name}
              </Text>
            </span>
          </div>
          <Text className={styles.noWorkspacesHint} data-testid={ElementIds.SIDEBAR_NO_WORKSPACES_HINT}>
            No workspaces yet
          </Text>
        </div>
      ))}
    </>
  );
};
