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

  // A navigation requested before the guest <webview> is ready to accept
  // loadURL. navigate() stashes the URL here instead of losing it, and
  // handleDomReady replays it once the guest fires dom-ready.
  const pendingNavigationUrlRef = useRef<string | null>(null);

  // Whether the guest has fired dom-ready. <webview>.loadURL throws "WebView
  // must be attached to the DOM and the dom-ready event emitted" until then, so
  // did-attach (which yields the webContentsId) is necessary but not
  // sufficient. navigate() gates on this so a URL requested in the brief
  // did-attach -> dom-ready window is held and replayed rather than sent to
  // loadURL, where it would reject and be silently swallowed.
  const isReadyRef = useRef(false);

  // Latest-ref pattern: the event-listener effect runs once with [], so it
  // captures the originally-passed callbacks. Reading via ref keeps it
  // pointing at the most recent props on every event.
  const onUrlChangeRef = useRef(onUrlChange);
  const setStatusRef = useRef(setStatus);
  useEffect(() => {
    onUrlChangeRef.current = onUrlChange;
    setStatusRef.current = setStatus;
  });

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
      // A freshly-attached guest has not fired dom-ready yet, so loadURL is not
      // usable until it does. Clearing the flag keeps "isReadyRef true" meaning
      // "the currently-attached guest has reached dom-ready" even when a guest
      // is recreated and re-attaches.
      isReadyRef.current = false;
    };

    const handleDomReady = (): void => {
      // dom-ready is the first point at which <webview>.loadURL is usable
      // (did-attach yields the webContentsId but the guest document is not yet
      // ready). Mark the guest ready and replay a navigation requested in the
      // did-attach -> dom-ready window, which would otherwise have been lost.
      // Replaying here also overrides the initial src="about:blank" load so the
      // user's first typed URL wins.
      isReadyRef.current = true;
      const pendingUrl = pendingNavigationUrlRef.current;
      if (pendingUrl !== null) {
        pendingNavigationUrlRef.current = null;
        webview.loadURL(pendingUrl).catch((error) => {
          console.warn("Failed to load pending URL in browser webview.", error);
        });
      }
    };

    webview.addEventListener("did-navigate", handleDidNavigate);
    webview.addEventListener("did-navigate-in-page", handleDidNavigateInPage);
    webview.addEventListener("did-start-loading", handleStartLoading);
    webview.addEventListener("did-stop-loading", handleStopLoading);
    webview.addEventListener("did-fail-load", handleDidFailLoad);
    webview.addEventListener("did-attach", handleDidAttach);
    webview.addEventListener("dom-ready", handleDomReady);

    return (): void => {
      webview.removeEventListener("did-navigate", handleDidNavigate);
      webview.removeEventListener("did-navigate-in-page", handleDidNavigateInPage);
      webview.removeEventListener("did-start-loading", handleStartLoading);
      webview.removeEventListener("did-stop-loading", handleStopLoading);
      webview.removeEventListener("did-fail-load", handleDidFailLoad);
      webview.removeEventListener("did-attach", handleDidAttach);
      webview.removeEventListener("dom-ready", handleDomReady);
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
      webviewRef.current?.loadURL(payload.url).catch((error) => {
        console.warn("Failed to load forwarded URL in browser webview.", error);
      });
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
    // Until the guest has fired dom-ready, loadURL throws ("WebView must be
    // attached to the DOM and the dom-ready event emitted") and the navigation
    // is silently lost. Stash the URL so handleDomReady can replay it once the
    // guest is ready. Last write wins, so the user's most recent typed URL is
    // the one that loads.
    if (!webview || !isReadyRef.current) {
      pendingNavigationUrlRef.current = url;
      return;
    }
    webview.loadURL(url).catch((error) => {
      console.warn("Failed to navigate browser webview.", error);
    });
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
