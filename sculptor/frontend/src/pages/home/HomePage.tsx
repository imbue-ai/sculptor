import { useAtomValue } from "jotai";
import type { ReactElement } from "react";
import { useRef, useState } from "react";

import { pluginHomeViewsAtom } from "~/plugins/pluginRegistry.ts";

import { useIsMobile } from "../../common/hooks/useLayoutMode.ts";
import { useWorkspaceNavigation } from "../../common/state/hooks/useWorkspaceNavigation.ts";
import { RecentWorkspaces } from "../add-workspace/components/RecentWorkspaces.tsx";
import { WorkspaceDrawer } from "../workspace/mobile/WorkspaceDrawer.tsx";
import styles from "./HomePage.module.scss";
import { BUILTIN_HOME_VIEW_ID, effectiveHomeViewIdAtom, homeViewOptionsAtom } from "./homeViews.ts";
import { HomeViewSwitcher } from "./HomeViewSwitcher.tsx";
import { MobileHomeHeader } from "./MobileHomeHeader.tsx";
import { RecentWorkspacesHomeView } from "./RecentWorkspacesHomeView.tsx";

export const HomePage = (): ReactElement => {
  const isMobile = useIsMobile();

  // Mobile Home state: its own ☰ header + drawer over the recent-workspaces list.
  // (Mobile does not yet surface the pluggable home-view switcher below.)
  const { handleWorkspaceClick, handleOpenInNewTab } = useWorkspaceNavigation();
  const searchInputRef = useRef<HTMLInputElement>(null);
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);

  // Desktop Home state: the pluggable home-view switcher + selected view.
  const options = useAtomValue(homeViewOptionsAtom);
  const effectiveId = useAtomValue(effectiveHomeViewIdAtom);
  const pluginHomeViews = useAtomValue(pluginHomeViewsAtom);

  // On mobile the global TopBar is suppressed (see PageLayout): Home carries its
  // own header with a ☰ that opens the same drawer (Home / Settings / workspaces)
  // as the Workspace view, keeping the recent-workspaces body below it.
  if (isMobile) {
    const recentWorkspaces = (
      <RecentWorkspaces
        searchInputRef={searchInputRef}
        autoFocusSearch={false}
        onWorkspaceClick={handleWorkspaceClick}
        onOpenInNewTab={handleOpenInNewTab}
        onEscapeToTitle={(): void => {
          searchInputRef.current?.focus();
        }}
      />
    );
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

  // Only surface the switcher once there is something to switch to: with no
  // plugin home views the page is the recent-workspaces list, exactly as before.
  const shouldShowSwitcher = options.length > 1;

  const SelectedView =
    effectiveId === BUILTIN_HOME_VIEW_ID
      ? RecentWorkspacesHomeView
      : (pluginHomeViews.find((view) => view.id === effectiveId)?.component ?? RecentWorkspacesHomeView);

  return (
    <div className={styles.root}>
      {shouldShowSwitcher && (
        <div className={styles.switcherBar}>
          <HomeViewSwitcher />
        </div>
      )}
      <div className={styles.body}>
        <SelectedView />
      </div>
    </div>
  );
};
