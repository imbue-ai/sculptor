import { useAtomValue } from "jotai";
import type { ReactElement } from "react";

import { pluginHomeViewsAtom } from "~/plugins/pluginRegistry.ts";

import styles from "./HomePage.module.scss";
import { BUILTIN_HOME_VIEW_ID, effectiveHomeViewIdAtom, homeViewOptionsAtom } from "./homeViews.ts";
import { HomeViewSwitcher } from "./HomeViewSwitcher.tsx";
import { RecentWorkspacesHomeView } from "./RecentWorkspacesHomeView.tsx";

export const HomePage = (): ReactElement => {
  const options = useAtomValue(homeViewOptionsAtom);
  const effectiveId = useAtomValue(effectiveHomeViewIdAtom);
  const pluginHomeViews = useAtomValue(pluginHomeViewsAtom);

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
