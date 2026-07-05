import { useSetAtom } from "jotai";
import { useEffect } from "react";

import { autoUpdateStatusAtom, updateChannelAtom } from "~/common/state/atoms/autoUpdate.ts";
import type { AutoUpdateStatus } from "~/common/types/backend.ts";

export const useAutoUpdateListener = (): void => {
  const setStatus = useSetAtom(autoUpdateStatusAtom);
  const setChannel = useSetAtom(updateChannelAtom);

  useEffect(() => {
    if (!window.sculptor) return;

    const handleStatus = (status: AutoUpdateStatus): void => {
      setStatus(status);
      if (status.type !== "disabled") {
        setChannel(status.channel);
      }
    };

    // Pull initial status so we don't depend on catching a push message
    // that may have been sent before this listener was registered.
    window.sculptor.getAutoUpdateStatus().then(handleStatus).catch(console.error);

    const wrappedCallback = window.sculptor.onAutoUpdateStatus(handleStatus);

    return (): void => {
      window.sculptor?.removeAutoUpdateStatusListener(wrappedCallback);
    };
  }, [setStatus, setChannel]);
};
