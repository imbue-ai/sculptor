import { useAtomValue } from "jotai";
import type { ReactElement } from "react";
import { useCallback, useMemo, useState } from "react";

import { autoUpdateStatusAtom } from "~/common/state/atoms/autoUpdate.ts";
import { useInstallUpdate } from "~/hooks/useInstallUpdate.ts";
import type { AutoUpdateStatus } from "~/shared/types.ts";

import { Toast, ToastType } from "./Toast.tsx";

type OpenToast = "download" | "ready" | "error" | null;

// Keep the download and ready toasts open until the user acts on them, rather
// than auto-dismissing on Radix's default timeout.
const PERSISTENT_TOAST_DURATION_MS = 999_999_999;
// Error toasts auto-dismiss after a few seconds so they don't linger.
const ERROR_TOAST_DURATION_MS = 5_000;

// Map an auto-update status to the toast it should surface, ignoring user
// dismissal (callers gate the download toast on the dismissed flag).
const toastForStatus = (status: AutoUpdateStatus | null): OpenToast => {
  if (status?.type === "available" || status?.type === "downloading") return "download";
  if (status?.type === "ready") return "ready";
  if (status?.type === "error") return "error";
  return null;
};

export const AutoUpdateToasts = (): ReactElement => {
  const status = useAtomValue(autoUpdateStatusAtom);
  const [openToast, setOpenToast] = useState<OpenToast>(() => toastForStatus(status));
  const [isDownloadDismissed, setIsDownloadDismissed] = useState(false);
  const { install, isInstalling } = useInstallUpdate();

  // Drive toast visibility from auto-update status transitions. Only one toast
  // is ever shown at a time. The download toast is suppressed after the user
  // dismisses it (tracked in state) so it doesn't re-appear on every status
  // poll while a download is in progress. We adjust state during render on a
  // status change (with a previous-value guard) rather than in an effect, so
  // there's no extra render between a status change and the toast update. See
  // docs/development/review/react.md (`no_effect_for_state_adjustment`).
  const [prevStatus, setPrevStatus] = useState(status);
  if (prevStatus !== status) {
    setPrevStatus(status);
    const nextToast = toastForStatus(status);
    if (nextToast === "download") {
      // While a download is in progress, stay suppressed if the user dismissed
      // the toast — otherwise it would re-open on every status poll.
      if (!isDownloadDismissed) {
        setOpenToast("download");
      }
    } else {
      if (nextToast === "ready") {
        setIsDownloadDismissed(false);
      }
      setOpenToast(nextToast);
    }
  }

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
      setIsDownloadDismissed(true);
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
        duration={PERSISTENT_TOAST_DURATION_MS}
      />
      <Toast
        open={openToast === "ready"}
        onOpenChange={handleDismiss}
        title={status?.type === "ready" ? `Update ready (v${status.version})` : "Update ready"}
        action={readyAction}
        duration={PERSISTENT_TOAST_DURATION_MS}
      />
      <Toast
        open={openToast === "error"}
        onOpenChange={handleDismiss}
        title={status?.type === "error" ? status.message : ""}
        type={ToastType.ERROR}
        duration={ERROR_TOAST_DURATION_MS}
      />
    </>
  );
};
