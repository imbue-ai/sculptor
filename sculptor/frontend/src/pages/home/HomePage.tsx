import { Flex } from "@radix-ui/themes";
import type { ReactElement } from "react";
import { useRef } from "react";

import { useWorkspaceNavigation } from "../../common/state/hooks/useWorkspaceNavigation.ts";
import { CollapsedSidebarToggle } from "../../components/nav/CollapsedSidebarToggle.tsx";
import { RecentWorkspaces } from "../add-workspace/components/RecentWorkspaces.tsx";
import styles from "./HomePage.module.scss";

export const HomePage = (): ReactElement => {
  const { handleWorkspaceClick, handleOpenInNewTab } = useWorkspaceNavigation();
  const searchInputRef = useRef<HTMLInputElement>(null);

  return (
    <>
      {/* The sidebar's expand toggle normally lives in the WorkspaceBanner,
          which this page doesn't render. Without this, collapsing the sidebar
          here would leave no way to reopen it. */}
      <CollapsedSidebarToggle />
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
    </>
  );
};
