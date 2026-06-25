import { useAtomValue, useSetAtom, useStore } from "jotai";
import type { CSSProperties, ReactElement } from "react";
import { useCallback, useEffect, useState } from "react";

import { ElementIds } from "~/api";

import { agentWebviewStateAtomFamily, browserPanelStateAtomFamily } from "./atoms";
import {
  browserViewPlacementAtomFamily,
  browserViewStatusAtomFamily,
  clearBrowserViewController,
  focusedBrowserWorkspaceIdAtom,
  setBrowserViewController,
} from "./browserViewRegistry";
import { useBrowserWebview } from "./useBrowserWebview";

// One <webview> per registered workspace, mounted under BrowserViewHost
// at the root of the React tree. Lifetime is tied to the registry, not
// to whichever route is currently rendered, so the webContents (and
// in-page state) survives panel-tab switches, zone visibility flips, and
// route detours through /settings or /ws/new.
export const BrowserViewSlot = ({ workspaceId }: { workspaceId: string }): ReactElement => {
  const setPanelState = useSetAtom(browserPanelStateAtomFamily(workspaceId));
  const setStatus = useSetAtom(browserViewStatusAtomFamily(workspaceId));
  const store = useStore();
  // Snapshot the persisted URL once at mount so subsequent persistUrl writes
  // don't re-render this slot (the toolbar reads liveUrl from the status atom).
  // Lazy useState (read-only snapshot, no setter needed); single-element
  // destructure trips react/hook-use-state, which wants a value+setter pair.
  // eslint-disable-next-line react/hook-use-state
  const [initialUrl] = useState(() => store.get(browserPanelStateAtomFamily(workspaceId)).currentUrl);

  const persistUrl = useCallback(
    (url: string) => {
      setPanelState((prev) => (prev.currentUrl === url ? prev : { ...prev, currentUrl: url }));
    },
    [setPanelState],
  );

  const { webviewRef, webContentsId, goBack, goForward, reload, navigate } = useBrowserWebview(
    initialUrl,
    persistUrl,
    setStatus,
  );

  useEffect(() => {
    setBrowserViewController(workspaceId, { goBack, goForward, reload, navigate });
    return (): void => {
      clearBrowserViewController(workspaceId);
    };
  }, [workspaceId, goBack, goForward, reload, navigate]);

  // Apply agent-issued webview commands. Lives on the slot (not BrowserPanel)
  // because the slot is mounted whenever the workspace is in the browser
  // registry — even if the user has a different panel tab active. Seq dedupe
  // is persisted in the same atom as the command itself so a command queued
  // before the slot first mounts still fires exactly once when the slot
  // comes up, and so the value survives BrowserViewSlot remounts.
  //
  // Gate on webContentsId so we don't call loadURL before the <webview> has
  // fired did-attach — without this, a command queued at slot-mount time
  // throws "WebView must be attached to the DOM and the dom-ready event
  // emitted". Once webContentsId flips non-null this effect re-runs.
  const agentWebviewState = useAtomValue(agentWebviewStateAtomFamily(workspaceId));
  useEffect(() => {
    const command = agentWebviewState.command;
    if (command === null) return;
    if (webContentsId === null) return;
    if (command.seq <= agentWebviewState.lastAppliedSeq) return;
    store.set(agentWebviewStateAtomFamily(workspaceId), (prev) => ({ ...prev, lastAppliedSeq: command.seq }));
    if (command.kind === "navigate" && command.url) {
      const navigatedUrl = command.url;
      navigate(navigatedUrl);
      setPanelState((prev) => (prev.currentUrl === navigatedUrl ? prev : { ...prev, currentUrl: navigatedUrl }));
    } else if (command.kind === "refresh") {
      reload();
    }
  }, [agentWebviewState, workspaceId, webContentsId, navigate, reload, setPanelState, store]);

  // Mirror the active workspace's webContentsId onto the global test
  // bridge so the existing Playwright fixture keeps working unchanged.
  const focusedWorkspaceId = useAtomValue(focusedBrowserWorkspaceIdAtom);
  const isFocused = focusedWorkspaceId === workspaceId;
  useEffect(() => {
    if (!isFocused || webContentsId === null) return;
    window.__BROWSER_PANEL_TEST__ = { webContentsId };
    return (): void => {
      delete window.__BROWSER_PANEL_TEST__;
    };
  }, [isFocused, webContentsId]);

  const placement = useAtomValue(browserViewPlacementAtomFamily(workspaceId));
  const partition = `persist:sculptor-browser-${workspaceId}`;
  const initialSrc = initialUrl === "" ? "about:blank" : initialUrl;

  // The <webview> guest renders with a transparent base, so a plain/unstyled
  // page (whose <body> has no background of its own) lets whatever is behind
  // the webview show through — namely Sculptor's themed app background. In dark
  // mode that paints the guest's default black text on a dark backdrop, which
  // is unreadable (SCU-1577). Give the element an opaque white background so
  // transparent pages render against the browser's normal white canvas,
  // independent of the Sculptor theme; pages with their own background paint
  // over it as usual.
  const style: CSSProperties = {
    backgroundColor: "#ffffff",
    ...(placement.visible && placement.bounds !== null
      ? {
          position: "fixed",
          left: placement.bounds.x,
          top: placement.bounds.y,
          width: placement.bounds.width,
          height: placement.bounds.height,
        }
      : { display: "none" }),
  };

  // Only the focused workspace's slot carries the BROWSER_WEBVIEW test id.
  const testId = isFocused ? ElementIds.BROWSER_WEBVIEW : undefined;

  return (
    <webview
      ref={webviewRef}
      /* eslint-disable-next-line react/no-unknown-property */
      partition={partition}
      /* eslint-disable-next-line react/no-unknown-property */
      allowpopups
      src={initialSrc}
      style={style}
      data-testid={testId}
      data-workspace-id={workspaceId}
    />
  );
};
