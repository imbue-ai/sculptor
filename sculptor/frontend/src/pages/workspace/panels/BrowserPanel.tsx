import { Flex, IconButton, Text, TextField, Tooltip } from "@radix-ui/themes";
import { useAtomValue } from "jotai";
import { AlertCircle, ArrowLeft, ArrowRight, Camera, RotateCw } from "lucide-react";
import type { ChangeEvent, FocusEvent, KeyboardEvent, ReactElement } from "react";
import { useCallback, useEffect, useRef, useState } from "react";

import { ElementIds } from "~/api";
import { useWorkspacePageParams } from "~/common/NavigateUtils";
import { registerPanelComponent } from "~/components/sections/registry/panelRegistry.ts";
import { activeWorkspaceIdAtom } from "~/components/sections/sectionAtoms.ts";
import { isElectron } from "~/electron/utils";

import { browserPanelStateAtomFamily } from "./browser/atoms";
import { browserViewStatusAtomFamily, getBrowserViewController } from "./browser/browserViewRegistry";
import { normalizeUrlInput } from "./browser/url";
import { useBrowserPanelPlacement } from "./browser/useBrowserPanelPlacement";
import styles from "./BrowserPanel.module.scss";

export const BrowserPanel = (): ReactElement => {
  if (!isElectron()) {
    return <BrowserPanelWebMode />;
  }
  return <BrowserPanelElectron />;
};

// Web-mode panel: renders the same toolbar shell as the Electron panel so the
// layout (and its alignment with the workspace banner) matches what users see
// in the desktop app, but every control is disabled and no <webview> mounts.
const BrowserPanelWebMode = (): ReactElement => (
  <div className={styles.panel} data-testid={ElementIds.BROWSER_PANEL}>
    <Flex align="center" gap="2" className={styles.toolbar}>
      <Tooltip content="Back">
        <IconButton variant="ghost" size="1" disabled aria-label="Back">
          <ArrowLeft size={16} />
        </IconButton>
      </Tooltip>
      <Tooltip content="Forward">
        <IconButton variant="ghost" size="1" disabled aria-label="Forward">
          <ArrowRight size={16} />
        </IconButton>
      </Tooltip>
      <Tooltip content="Refresh">
        <IconButton variant="ghost" size="1" disabled aria-label="Refresh">
          <RotateCw size={16} />
        </IconButton>
      </Tooltip>
      <TextField.Root
        size="1"
        className={styles.addressInput}
        placeholder="Enter a URL (e.g. localhost:3000)"
        disabled
      />
      <Tooltip content="Screenshot to clipboard">
        <IconButton variant="ghost" size="1" disabled aria-label="Screenshot to clipboard">
          <Camera size={16} />
        </IconButton>
      </Tooltip>
    </Flex>
    <div className={styles.placeholder}>
      <Text size="2" data-testid={ElementIds.BROWSER_WEB_MODE_PLACEHOLDER}>
        Browser panel requires the desktop app.
      </Text>
    </div>
  </div>
);

// The Electron panel is a thin shell: a toolbar that reads status from
// browserViewStatusAtomFamily and dispatches actions through the controller
// registry, plus a placeholder div whose bounds drive the active workspace's
// <webview> position. The webview itself lives in BrowserViewHost (mounted
// at the app root) and survives panel mount/unmount.
const BrowserPanelElectron = (): ReactElement => {
  const { workspaceID } = useWorkspacePageParams();
  const placeholderRef = useRef<HTMLDivElement>(null);
  useBrowserPanelPlacement(workspaceID, placeholderRef);

  const persistedState = useAtomValue(browserPanelStateAtomFamily(workspaceID));
  const status = useAtomValue(browserViewStatusAtomFamily(workspaceID));
  const liveUrl = status.currentUrl !== "" ? status.currentUrl : persistedState.currentUrl;

  // editedUrl is the user's in-progress override; while non-null we ignore
  // liveUrl so an in-page redirect can't clobber what the user is typing.
  // The render-time adjustment below drops the override whenever liveUrl
  // actually changes (e.g. after navigation lands), so the bar follows the
  // real current URL — including redirects — once the webview catches up.
  const [editedUrl, setEditedUrl] = useState<string | null>(null);
  const [prevLiveUrl, setPrevLiveUrl] = useState(liveUrl);
  if (prevLiveUrl !== liveUrl) {
    setPrevLiveUrl(liveUrl);
    if (editedUrl !== null) setEditedUrl(null);
  }
  const addressInput = editedUrl ?? liveUrl;

  const urlInputRef = useRef<HTMLInputElement>(null);
  // Focus the URL input every time the panel mounts (i.e. every time it
  // opens), regardless of whether the workspace already has a persisted
  // URL. The empty dependency array keeps this from re-firing on rerenders
  // triggered by in-page navigation events.
  useEffect(() => {
    urlInputRef.current?.focus();
  }, []);

  const [urlError, setUrlError] = useState<string | null>(null);

  const handleAddressKeyDown = (event: KeyboardEvent<HTMLInputElement>): void => {
    if (event.key === "Escape") {
      setEditedUrl(null);
      setUrlError(null);
      event.currentTarget.blur();
      return;
    }
    if (event.key !== "Enter") return;
    const result = normalizeUrlInput(addressInput);
    if (result.kind === "empty") return;
    if (result.kind === "invalid") {
      setUrlError(result.reason);
      return;
    }
    setUrlError(null);
    // Show the typed URL in the bar until did-navigate updates liveUrl,
    // at which point the render-time adjustment clears editedUrl.
    setEditedUrl(result.url);
    getBrowserViewController(workspaceID)?.navigate(result.url);
  };

  const handleAddressFocus = (event: FocusEvent<HTMLInputElement>): void => {
    event.currentTarget.select();
  };

  const handleAddressChange = (event: ChangeEvent<HTMLInputElement>): void => {
    setEditedUrl(event.target.value);
    if (urlError !== null) setUrlError(null);
  };

  const handleBack = useCallback((): void => {
    getBrowserViewController(workspaceID)?.goBack();
  }, [workspaceID]);
  const handleForward = useCallback((): void => {
    getBrowserViewController(workspaceID)?.goForward();
  }, [workspaceID]);
  const handleReload = useCallback((): void => {
    getBrowserViewController(workspaceID)?.reload();
  }, [workspaceID]);

  const handleScreenshot = useCallback((): void => {
    if (status.webContentsId === null) return;
    void window.sculptor?.captureBrowserPanelToClipboard(status.webContentsId);
  }, [status.webContentsId]);

  return (
    <div className={styles.panel} data-testid={ElementIds.BROWSER_PANEL} data-workspace-id={workspaceID}>
      <Flex align="center" gap="2" className={styles.toolbar}>
        <Tooltip content="Back">
          <IconButton
            variant="ghost"
            size="1"
            disabled={!status.canGoBack}
            onClick={handleBack}
            data-testid={ElementIds.BROWSER_BACK_BTN}
            aria-label="Back"
          >
            <ArrowLeft size={16} />
          </IconButton>
        </Tooltip>
        <Tooltip content="Forward">
          <IconButton
            variant="ghost"
            size="1"
            disabled={!status.canGoForward}
            onClick={handleForward}
            data-testid={ElementIds.BROWSER_FORWARD_BTN}
            aria-label="Forward"
          >
            <ArrowRight size={16} />
          </IconButton>
        </Tooltip>
        <Tooltip content="Refresh">
          <IconButton
            variant="ghost"
            size="1"
            onClick={handleReload}
            data-testid={ElementIds.BROWSER_REFRESH_BTN}
            aria-label="Refresh"
          >
            <RotateCw size={16} />
          </IconButton>
        </Tooltip>
        <TextField.Root
          size="1"
          className={styles.addressInput}
          value={addressInput}
          placeholder="Enter a URL (e.g. localhost:3000)"
          onChange={handleAddressChange}
          onKeyDown={handleAddressKeyDown}
          onFocus={handleAddressFocus}
          data-testid={ElementIds.BROWSER_URL_INPUT}
          ref={urlInputRef}
        />
        <Tooltip content="Screenshot to clipboard">
          <IconButton
            variant="ghost"
            size="1"
            disabled={status.webContentsId === null}
            onClick={handleScreenshot}
            data-testid={ElementIds.BROWSER_SCREENSHOT_BTN}
            aria-label="Screenshot to clipboard"
          >
            <Camera size={16} />
          </IconButton>
        </Tooltip>
      </Flex>
      {urlError !== null && (
        <Flex align="center" gap="2" className={styles.errorBar} role="alert">
          <AlertCircle size={14} />
          <Text size="1" data-testid={ElementIds.BROWSER_URL_ERROR}>
            {urlError}
          </Text>
        </Flex>
      )}
      <div ref={placeholderRef} className={styles.webviewContainer} />
    </div>
  );
};

// The single-instance Browser panel for the section/panel shell: a thin, no-prop
// wrapper that gates on the active workspace and renders the existing browser
// surface. There is no opt-in/enable concept — it is just a registered panel; the
// webview's isolation and in-page-state persistence are owned by BrowserViewHost and
// the browser registry, which survive panel mount/unmount.
const BrowserPanelForShell = (): ReactElement | null => {
  const workspaceId = useAtomValue(activeWorkspaceIdAtom);
  if (workspaceId === null) {
    return null;
  }
  return <BrowserPanel key={workspaceId} />;
};

registerPanelComponent("browser", BrowserPanelForShell);
