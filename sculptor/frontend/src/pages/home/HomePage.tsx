import { Flex } from "@radix-ui/themes";
import { useAtom } from "jotai";
import type { ReactElement } from "react";
import { useEffect, useRef } from "react";
import { useSearchParams } from "react-router-dom";

import { useWorkspaceNavigation } from "../../common/state/hooks/useWorkspaceNavigation.ts";
import { newWorkspaceModalAutoOpenedAtom } from "../../components/NewWorkspaceModal/atoms.ts";
import { useNewWorkspaceModal } from "../../components/NewWorkspaceModal/hooks.ts";
import { RecentWorkspaces } from "../add-workspace/components/RecentWorkspaces.tsx";
import styles from "./HomePage.module.scss";

export const HomePage = (): ReactElement => {
  const { handleWorkspaceClick, handleOpenInNewTab } = useWorkspaceNavigation();
  const searchInputRef = useRef<HTMLInputElement>(null);
  const [searchParams, setSearchParams] = useSearchParams();
  const { open: openNewWorkspaceModal } = useNewWorkspaceModal();
  const [hasAutoOpened, setHasAutoOpened] = useAtom(newWorkspaceModalAutoOpenedAtom);

  // First-load auto-open: rootLoader appends `?firstLoad=true` when it
  // had no MRU / recent workspace to redirect to, so the user landed
  // here as a default. Pop the new-workspace modal so they can get
  // started immediately. Fires once per app boot — re-navigating to
  // /home later doesn't re-pop.
  useEffect(() => {
    if (hasAutoOpened) return;
    if (searchParams.get("firstLoad") !== "true") return;
    setHasAutoOpened(true);
    openNewWorkspaceModal("auto");
    // Strip the marker from the URL so a manual reload of /home doesn't
    // re-trigger the auto-open.
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        next.delete("firstLoad");
        return next;
      },
      { replace: true },
    );
  }, [hasAutoOpened, searchParams, setSearchParams, setHasAutoOpened, openNewWorkspaceModal]);

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
