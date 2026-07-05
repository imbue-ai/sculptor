import { Flex } from "@radix-ui/themes";
import type { ReactElement } from "react";
import { useRef } from "react";

import { useWorkspaceNavigation } from "../../common/state/hooks/useWorkspaceNavigation.ts";
import { RecentWorkspaces } from "../addWorkspace/components/RecentWorkspaces.tsx";
import styles from "./RecentWorkspacesHomeView.module.scss";

/**
 * The built-in homepage view: a centered, searchable list of recent workspaces.
 * Registered under {@link BUILTIN_HOME_VIEW_ID} and always the fallback view, so
 * the homepage looks unchanged when no plugin contributes an alternative.
 */
export const RecentWorkspacesHomeView = (): ReactElement => {
  const { handleWorkspaceClick, handleOpenInNewTab } = useWorkspaceNavigation();
  const searchInputRef = useRef<HTMLInputElement>(null);

  return (
    <Flex direction="column" align="center" className={styles.container}>
      <div className={styles.content}>
        <RecentWorkspaces
          searchInputRef={searchInputRef}
          autoFocusSearch
          onWorkspaceClick={handleWorkspaceClick}
          onOpenInNewTab={handleOpenInNewTab}
          onEscapeToTitle={(): void => {
            searchInputRef.current?.focus();
          }}
        />
      </div>
    </Flex>
  );
};
