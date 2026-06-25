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

  const install = useCallback((): void => {
    if (isInstalling) return;
    setIsInstalling(true);

    posthog.capture("auto_update.install_clicked", {
      target_version: status && (status.type === "ready" || status.type === "available") ? status.version : null,
      update_channel: status && "channel" in status ? status.channel : null,
    });

    window.sculptor
      ?.installUpdate()
      .then((accepted) => {
        if (!accepted) {
          setIsInstalling(false);
        }
        // If accepted, the app is shutting down — leave the loading state on.
      })
      .catch((error: unknown) => {
        // The install request failed; clear the loading state so the user can retry.
        console.error(error);
        setIsInstalling(false);
      });
  }, [isInstalling, setIsInstalling, status]);

  return { install, isInstalling };
};
