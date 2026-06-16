import { Flex } from "@radix-ui/themes";
import type { ReactElement } from "react";
import { useRef } from "react";

import { useWorkspaceNavigation } from "../../common/state/hooks/useWorkspaceNavigation.ts";
import styles from "./HomePage.module.scss";
import { RecentWorkspaces } from "./RecentWorkspaces.tsx";

export const HomePage = (): ReactElement => {
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
