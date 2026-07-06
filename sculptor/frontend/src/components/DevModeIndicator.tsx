import { Tooltip } from "@radix-ui/themes";
import { type ReactElement, useEffect, useState } from "react";

import type { SculptorDevInfo } from "~/shared/types.ts";

import styles from "./DevModeIndicator.module.scss";

// In Electron the recolored dock icon, label, and workspace id arrive from
// the GET_DEV_INFO IPC channel — the same NativeImage already used for the
// dock icon, serialized at full resolution. The browser scales it via CSS.
// When running in pure-browser dev (Vite dev server, no Electron), there is no
// icon, so we fall back to a small colored dot gated on import.meta.env.DEV.
export const DevModeIndicator = (): ReactElement | null => {
  const [devInfo, setDevInfo] = useState<SculptorDevInfo | null>(null);
  const isViteDev = import.meta.env.DEV;

  useEffect(() => {
    // Guard against partial `window.sculptor` shapes — older preload scripts
    // and the browser-mode auto-update test mock both expose only a subset of
    // the API. The sidebar footer mounts this on every route, including pages
    // whose tests stub out `window.sculptor` with a different surface, so a
    // missing method must not throw.
    if (typeof window.sculptor?.getDevInfo !== "function") return;
    let isCancelled = false;
    window.sculptor.getDevInfo().then((info) => {
      if (!isCancelled) setDevInfo(info);
    });
    return (): void => {
      isCancelled = true;
    };
  }, []);

  if (!devInfo && !isViteDev) return null;

  const iconDataUrl = devInfo?.iconDataUrl ?? null;
  const workspaceId = devInfo?.workspaceId ?? null;

  const tooltipContent = (
    <span className={styles.tooltipContent}>
      {iconDataUrl && <img className={styles.tooltipIcon} src={iconDataUrl} alt="" aria-hidden="true" />}
      <span className={styles.tooltipText}>
        <span>Running from source</span>
        {workspaceId && <span>Workspace: {workspaceId}</span>}
      </span>
    </span>
  );

  // Compact dev-source indicator that sits inline beside the version string:
  // the recolored Electron icon when it's available, otherwise a small colored
  // dot (matching VersionPopover's update dot). Full detail — source running
  // plus the workspace id — lives in the tooltip.
  return (
    <Tooltip content={tooltipContent}>
      <span className={styles.root} data-testid="dev-mode-indicator">
        {iconDataUrl ? (
          <img className={styles.icon} src={iconDataUrl} alt="" aria-hidden="true" />
        ) : (
          <span className={styles.dot} aria-hidden="true" />
        )}
      </span>
    </Tooltip>
  );
};
