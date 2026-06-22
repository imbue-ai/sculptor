import type { DidFailLoadEvent, DidNavigateEvent, DidNavigateInPageEvent, WebviewTag } from "electron";
import type { RefObject } from "react";
import { useCallback, useEffect, useRef, useState } from "react";

import type { BrowserViewStatus } from "./browserViewRegistry";

export type BrowserWebviewController = {
  webviewRef: RefObject<WebviewTag | null>;
  webContentsId: number | null;
  goBack: () => void;
  goForward: () => void;
  reload: () => void;
  navigate: (url: string) => void;
};

const INITIAL_STATUS: Omit<BrowserViewStatus, "currentUrl"> = {
  canGoBack: false,
  canGoForward: false,
  isLoading: false,
  webContentsId: null,
};

export const useBrowserWebview = (
  initialUrl: string,
  onUrlChange: (url: string) => void,
  setStatus: (status: BrowserViewStatus) => void,
): BrowserWebviewController => {
  const webviewRef = useRef<WebviewTag>(null);
  const [webContentsId, setWebContentsId] = useState<number | null>(null);

  // Status flows out via the setStatus callback rather than React state so
  // navigation events (which fire on every URL hop) don't re-render the
  // slot. The ref holds the running value so partial updates can merge.
  const statusRef = useRef<BrowserViewStatus>({ ...INITIAL_STATUS, currentUrl: initialUrl });

  // Latest-ref pattern: the event-listener effect runs once with [], so it
  // captures the originally-passed callbacks. Reading via ref keeps it
  // pointing at the most recent props on every event.
  const onUrlChangeRef = useRef(onUrlChange);
  onUrlChangeRef.current = onUrlChange;
  const setStatusRef = useRef(setStatus);
  setStatusRef.current = setStatus;

  useEffect(() => {
    const webview = webviewRef.current;
    if (!webview) return;

    const publishStatus = (patch: Partial<BrowserViewStatus>): void => {
      statusRef.current = { ...statusRef.current, ...patch };
      setStatusRef.current(statusRef.current);
    };

    const handleDidNavigate = (event: DidNavigateEvent): void => {
      publishStatus({
        currentUrl: event.url,
        canGoBack: webview.canGoBack(),
        canGoForward: webview.canGoForward(),
      });
      onUrlChangeRef.current(event.url);
    };

    const handleDidNavigateInPage = (event: DidNavigateInPageEvent): void => {
      publishStatus({
        currentUrl: event.url,
        canGoBack: webview.canGoBack(),
        canGoForward: webview.canGoForward(),
      });
      onUrlChangeRef.current(event.url);
    };

    const handleStartLoading = (): void => {
      publishStatus({ isLoading: true });
    };

    const handleStopLoading = (): void => {
      publishStatus({
        isLoading: false,
        canGoBack: webview.canGoBack(),
        canGoForward: webview.canGoForward(),
      });
    };

    const handleDidFailLoad = (event: DidFailLoadEvent): void => {
      if (event.isMainFrame) publishStatus({ isLoading: false });
    };

    const handleDidAttach = (): void => {
      const id = webview.getWebContentsId();
      setWebContentsId(id);
      publishStatus({ webContentsId: id });
    };

    webview.addEventListener("did-navigate", handleDidNavigate);
    webview.addEventListener("did-navigate-in-page", handleDidNavigateInPage);
    webview.addEventListener("did-start-loading", handleStartLoading);
    webview.addEventListener("did-stop-loading", handleStopLoading);
    webview.addEventListener("did-fail-load", handleDidFailLoad);
    webview.addEventListener("did-attach", handleDidAttach);

    return (): void => {
      webview.removeEventListener("did-navigate", handleDidNavigate);
      webview.removeEventListener("did-navigate-in-page", handleDidNavigateInPage);
      webview.removeEventListener("did-start-loading", handleStartLoading);
      webview.removeEventListener("did-stop-loading", handleStopLoading);
      webview.removeEventListener("did-fail-load", handleDidFailLoad);
      webview.removeEventListener("did-attach", handleDidAttach);
    };
  }, []);

  // Popup interception: when the guest page tries to open a target="_blank"
  // link (or window.open), the main process denies the popup and forwards
  // the URL here via IPC. We navigate the matching panel's webview instead.
  useEffect(() => {
    if (webContentsId === null) return;
    const api = window.sculptor;
    if (!api?.onBrowserPanelOpenInPanel || !api.removeBrowserPanelOpenInPanelListener) return;
    const listener = api.onBrowserPanelOpenInPanel((payload) => {
      if (payload.webContentsId !== webContentsId) return;
      webviewRef.current?.loadURL(payload.url).catch(() => {});
    });
    return (): void => {
      api.removeBrowserPanelOpenInPanelListener?.(listener);
    };
  }, [webContentsId]);

  const goBack = useCallback((): void => {
    const webview = webviewRef.current;
    if (webview && webview.canGoBack()) webview.goBack();
  }, []);

  const goForward = useCallback((): void => {
    const webview = webviewRef.current;
    if (webview && webview.canGoForward()) webview.goForward();
  }, []);

  const reload = useCallback((): void => {
    webviewRef.current?.reload();
  }, []);

  const navigate = useCallback((url: string): void => {
    const webview = webviewRef.current;
    if (!webview) return;
    webview.loadURL(url).catch(() => {});
  }, []);

  return {
    webviewRef,
    webContentsId,
    goBack,
    goForward,
    reload,
    navigate,
  };
};
