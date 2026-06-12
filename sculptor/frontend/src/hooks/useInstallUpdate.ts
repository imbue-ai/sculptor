import { useAtom, useAtomValue } from "jotai";
import { posthog } from "posthog-js";
import { useCallback } from "react";

import { autoUpdateStatusAtom, isInstallingUpdateAtom } from "~/common/state/atoms/autoUpdate.ts";

type UseInstallUpdate = {
  install: () => void;
  isInstalling: boolean;
};

export const useInstallUpdate = (): UseInstallUpdate => {
  const [isInstalling, setIsInstalling] = useAtom(isInstallingUpdateAtom);
  const status = useAtomValue(autoUpdateStatusAtom);

  const install = useCallback(() => {
    if (isInstalling) return;
    setIsInstalling(true);

    posthog.capture("auto_update.install_clicked", {
      target_version: status && (status.type === "ready" || status.type === "available") ? status.version : null,
      update_channel: status && "channel" in status ? status.channel : null,
    });

    window.sculptor?.installUpdate().then((accepted) => {
      if (!accepted) {
        setIsInstalling(false);
      }
      // If accepted, the app is shutting down — leave the loading state on.
    });
  }, [isInstalling, setIsInstalling, status]);

  return { install, isInstalling };
};
