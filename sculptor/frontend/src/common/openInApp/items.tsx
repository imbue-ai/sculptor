import type { ComponentType, ReactElement } from "react";

import { type ExternalApp, openPathInApp } from "~/api";
import cursorIcon from "~/assets/appIcons/cursor.png";
import finderIcon from "~/assets/appIcons/finder.png";
import ghosttyIcon from "~/assets/appIcons/ghostty.png";
import itermIcon from "~/assets/appIcons/iterm.png";
import pycharmIcon from "~/assets/appIcons/pycharm.png";
import terminalIcon from "~/assets/appIcons/terminal.png";
import vscodeIcon from "~/assets/appIcons/vscode.png";
import { isMac } from "~/electron/platform";

export type OpenWithItem = {
  app: ExternalApp;
  label: string;
  /** PNG asset URL — used for `<img>` rendering in dropdown menus. */
  icon: string;
  /**
   * Component-shaped wrapper around the PNG, rendered by consumers like
   * the command palette that pass `<Icon size={n} />` instead of an
   * `<img>` tag. Memoized at module load — the same component identity
   * is reused on every render so React doesn't see icon churn.
   */
  IconComponent: ComponentType<{ size?: number }>;
};

const makeAppIconComponent = (src: string, alt: string): ComponentType<{ size?: number }> => {
  const Component = ({ size = 14 }: { size?: number }): ReactElement => (
    <img src={src} alt={alt} width={size} height={size} />
  );
  Component.displayName = `AppIcon(${alt})`;
  return Component;
};

// "Open With" app list is only shown on macOS for now. The backend supports
// Linux (via shutil.which + xdg-open), but we haven't been able to verify
// the UI on Linux yet, so we hide the list there.
export const OPEN_WITH_ITEMS_MAC: ReadonlyArray<OpenWithItem> = [
  { app: "finder", label: "Finder", icon: finderIcon, IconComponent: makeAppIconComponent(finderIcon, "Finder") },
  { app: "cursor", label: "Cursor", icon: cursorIcon, IconComponent: makeAppIconComponent(cursorIcon, "Cursor") },
  { app: "vscode", label: "VS Code", icon: vscodeIcon, IconComponent: makeAppIconComponent(vscodeIcon, "VS Code") },
  { app: "pycharm", label: "PyCharm", icon: pycharmIcon, IconComponent: makeAppIconComponent(pycharmIcon, "PyCharm") },
  { app: "ghostty", label: "Ghostty", icon: ghosttyIcon, IconComponent: makeAppIconComponent(ghosttyIcon, "Ghostty") },
  { app: "iterm", label: "iTerm", icon: itermIcon, IconComponent: makeAppIconComponent(itermIcon, "iTerm") },
  {
    app: "terminal",
    label: "Terminal",
    icon: terminalIcon,
    IconComponent: makeAppIconComponent(terminalIcon, "Terminal"),
  },
];

export const getOpenWithItems = (): ReadonlyArray<OpenWithItem> => {
  return isMac() ? OPEN_WITH_ITEMS_MAC : [];
};

const PREFERRED_APP_STORAGE_KEY = "sculptor-preferred-open-app";

export const getPreferredApp = (): ExternalApp | null => {
  const stored = localStorage.getItem(PREFERRED_APP_STORAGE_KEY);
  const match = getOpenWithItems().find((item) => item.app === stored);
  return match ? match.app : null;
};

export const savePreferredApp = (app: ExternalApp): void => {
  localStorage.setItem(PREFERRED_APP_STORAGE_KEY, app);
};

export type OpenInAppResult = {
  success: boolean;
  errorMessage?: string | null;
};

/**
 * Calls the backend `/api/v1/open-path-in-app` endpoint and normalizes the
 * outcome. Returns `{ success: false, errorMessage }` on either an HTTP
 * failure or a backend-level "not installed" / "path not found" error.
 *
 * Callers are responsible for surfacing the error to the user (e.g. via a
 * toast or alert dialog).
 */
export const openPathInExternalApp = async (path: string, app: ExternalApp): Promise<OpenInAppResult> => {
  try {
    const response = await openPathInApp({
      body: { path, app },
      meta: { skipWsAck: true },
    });
    if (!response.data.success) {
      return {
        success: false,
        errorMessage: response.data.errorMessage ?? null,
      };
    }
    return { success: true };
  } catch {
    return { success: false, errorMessage: null };
  }
};
