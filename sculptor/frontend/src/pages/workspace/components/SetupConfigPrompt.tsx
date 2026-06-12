import { Button } from "@radix-ui/themes";
import { TerminalSquareIcon } from "lucide-react";
import type { ReactElement } from "react";
import { useCallback } from "react";

import { useActiveProjectID } from "~/common/NavigateUtils";
import { useOpenSettings } from "~/common/state/hooks/useOpenSettings";

import styles from "./ChatIntro.module.scss";

export const SetupConfigPrompt = (): ReactElement => {
  const projectId = useActiveProjectID();
  const openSettings = useOpenSettings();

  const handleOpenSettings = useCallback((): void => {
    if (projectId !== null) {
      openSettings("repositories", projectId);
    } else {
      openSettings("repositories");
    }
  }, [projectId, openSettings]);

  return (
    <div data-testid="setup-config-prompt" className={styles.detailRow}>
      <TerminalSquareIcon size={14} className={styles.detailIcon} />
      <span>
        <Button variant="ghost" size="1" data-testid="setup-config-settings-link" onClick={handleOpenSettings}>
          Configure a workspace setup command
        </Button>
      </span>
    </div>
  );
};
