import { Flex } from "@radix-ui/themes";
import type { ReactElement } from "react";
import { useRef } from "react";

import { useWorkspaceNavigation } from "../../common/state/hooks/useWorkspaceNavigation.ts";
import { RecentWorkspaces } from "../add-workspace/components/RecentWorkspaces.tsx";
import styles from "./HomePage.module.scss";

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
