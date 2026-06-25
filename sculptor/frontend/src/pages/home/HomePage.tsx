import { Flex } from "@radix-ui/themes";
import type { ReactElement } from "react";
import { useRef, useState } from "react";

import { useIsMobile } from "../../common/hooks/useLayoutMode.ts";
import { useWorkspaceNavigation } from "../../common/state/hooks/useWorkspaceNavigation.ts";
import { RecentWorkspaces } from "../add-workspace/components/RecentWorkspaces.tsx";
import { WorkspaceDrawer } from "../workspace/mobile/WorkspaceDrawer.tsx";
import styles from "./HomePage.module.scss";
import { MobileHomeHeader } from "./MobileHomeHeader.tsx";

export const HomePage = (): ReactElement => {
  const { handleWorkspaceClick, handleOpenInNewTab } = useWorkspaceNavigation();
  const searchInputRef = useRef<HTMLInputElement>(null);
  const isMobile = useIsMobile();
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);

  const recentWorkspaces = (
    <RecentWorkspaces
      searchInputRef={searchInputRef}
      autoFocusSearch={!isMobile}
      onWorkspaceClick={handleWorkspaceClick}
      onOpenInNewTab={handleOpenInNewTab}
      onEscapeToTitle={(): void => {
        searchInputRef.current?.focus();
      }}
    />
  );

  // On mobile the global TopBar is suppressed (see PageLayout): Home carries its
  // own header with a ☰ that opens the same drawer (Home / Settings / workspaces)
  // as the Workspace view, keeping the existing recent-workspaces body below it.
  if (isMobile) {
    return (
      <div className={`mobileTheme ${styles.mobileShell}`}>
        <MobileHomeHeader onOpenDrawer={() => setIsDrawerOpen(true)} />
        <div className={styles.mobileContent}>{recentWorkspaces}</div>

        <div
          className={`${styles.backdrop} ${isDrawerOpen ? styles.open : ""}`}
          onClick={() => setIsDrawerOpen(false)}
          aria-hidden={!isDrawerOpen}
        />
        <WorkspaceDrawer isOpen={isDrawerOpen} onClose={() => setIsDrawerOpen(false)} />
      </div>
    );
  }

  return (
    <Flex direction="column" align="center" className={styles.container}>
      <div className={styles.content}>{recentWorkspaces}</div>
    </Flex>
  );
};
