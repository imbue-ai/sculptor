import { useAtomValue } from "jotai";
import type { ReactElement } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { autoUpdateStatusAtom } from "~/common/state/atoms/autoUpdate.ts";
import { useInstallUpdate } from "~/hooks/useInstallUpdate.ts";

import { Toast, ToastType } from "./Toast.tsx";

type OpenToast = "download" | "ready" | "error" | null;

export const AutoUpdateToasts = (): ReactElement => {
  const status = useAtomValue(autoUpdateStatusAtom);
  const [openToast, setOpenToast] = useState<OpenToast>(null);
  const downloadDismissedRef = useRef(false);
  const { install, isInstalling } = useInstallUpdate();

  // Drive toast visibility from auto-update status transitions. Only one toast
  // is ever shown at a time. The download toast is suppressed after the user
  // dismisses it (tracked via ref) so it doesn't re-appear on every status
  // poll while a download is in progress.
  useEffect(() => {
    if (status?.type === "available" || status?.type === "downloading") {
      if (!downloadDismissedRef.current) {
        setOpenToast("download");
      }
    } else if (status?.type === "ready") {
      setOpenToast("ready");
      downloadDismissedRef.current = false;
    } else if (status?.type === "error") {
      setOpenToast("error");
    } else {
      setOpenToast(null);
    }
  }, [status]);

  const downloadTitle =
    status?.type === "downloading"
      ? `Downloading update... ${status.percent}%`
      : status?.type === "available"
        ? `Downloading update v${status.version}...`
        : "";

  // Stable callbacks/objects so the memoized <Toast> instances bail out instead
  // of re-rendering on every unrelated commit while they sit closed. (SCU-1455)
  const handleDownloadOpenChange = useCallback((open: boolean) => {
    if (!open) {
      setOpenToast(null);
      downloadDismissedRef.current = true;
    }
  }, []);
  const handleDismiss = useCallback((open: boolean) => {
    if (!open) setOpenToast(null);
  }, []);
  const readyAction = useMemo(
    () => ({
      label: isInstalling ? "Restarting..." : "Install and restart",
      handleClick: install,
    }),
    [isInstalling, install],
  );

  return (
    <>
      <Toast
        open={openToast === "download"}
        onOpenChange={handleDownloadOpenChange}
        title={downloadTitle}
        duration={999999999}
      />
      <Toast
        open={openToast === "ready"}
        onOpenChange={handleDismiss}
        title={status?.type === "ready" ? `Update ready (v${status.version})` : "Update ready"}
        action={readyAction}
        duration={999999999}
      />
      <Toast
        open={openToast === "error"}
        onOpenChange={handleDismiss}
        title={status?.type === "error" ? status.message : ""}
        type={ToastType.ERROR}
        duration={5000}
      />
    </>
  );
};
