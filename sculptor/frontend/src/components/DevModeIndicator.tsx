import { Tooltip } from "@radix-ui/themes";
import { type ReactElement, useEffect, useState } from "react";

import devIconUrl from "~/assets/logos/dev_icon.png";
import type { SculptorDevInfo } from "~/shared/types.ts";

import styles from "./DevModeIndicator.module.scss";

// In Electron the recolored dock icon, label, and workspace id arrive from
// the GET_DEV_INFO IPC channel — the same NativeImage already used for the
// dock icon, serialized at full resolution. The browser scales it via CSS.
// When running in pure-browser dev (Vite dev server, no Electron), that IPC
// channel is absent, so we fall back to `devIconUrl`: a pre-rendered copy of
// that dev icon. This fallback is only rendered when `import.meta.env.DEV` is true.
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
  // the recolored Electron dock icon when it's available, otherwise a pre-rendered
  // copy of that same dev icon — the production app icon recolored with a "dev"
  // label, mirroring devIcon.ts so it matches the macOS dock icon. Full detail —
  // source running plus the workspace id — lives in the tooltip.
  return (
    <Tooltip content={tooltipContent}>
      <span className={styles.root} data-testid="dev-mode-indicator">
        <img className={styles.icon} src={iconDataUrl ?? devIconUrl} alt="" aria-hidden="true" />
      </span>
    </Tooltip>
  );
};
