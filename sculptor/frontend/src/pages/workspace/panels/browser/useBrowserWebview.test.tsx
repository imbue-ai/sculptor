import { act, cleanup, render } from "@testing-library/react";
import type { ReactElement } from "react";
import { useEffect } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { type BrowserWebviewController, useBrowserWebview } from "./useBrowserWebview";

// A stand-in for the Electron <webview> guest element. jsdom renders <webview>
// as a real EventTarget (so the hook's addEventListener/dispatchEvent wiring
// works), which we augment with the guest methods the hook calls. The methods
// are attached after render because the hook's effect only references the
// element to register listeners — it invokes loadURL/getWebContentsId later,
// from inside the event handlers the tests drive below.
type FakeWebview = HTMLElement & {
  loadURL: ReturnType<typeof vi.fn>;
  reload: ReturnType<typeof vi.fn>;
  getWebContentsId: () => number;
  canGoBack: () => boolean;
  canGoForward: () => boolean;
};

let captured: BrowserWebviewController | null = null;

const Harness = (): ReactElement => {
  const controller = useBrowserWebview("", vi.fn(), vi.fn());
  const { webviewRef } = controller;
  // Capture the controller from an effect (not during render) so the test can
  // drive navigate() and reach the bound element.
  useEffect(() => {
    captured = controller;
  });
  return <webview ref={webviewRef} />;
};

const mountWebview = (): FakeWebview => {
  render(<Harness />);
  const webview = captured?.webviewRef.current as unknown as FakeWebview;
  webview.loadURL = vi.fn(() => Promise.resolve());
  webview.reload = vi.fn();
  webview.getWebContentsId = (): number => 42;
  webview.canGoBack = (): boolean => false;
  webview.canGoForward = (): boolean => false;
  return webview;
};

afterEach(() => {
  cleanup();
  captured = null;
});

describe("useBrowserWebview navigation readiness", () => {
  it("defers loadURL until the guest fires dom-ready, then replays the pending URL", () => {
    const webview = mountWebview();

    // The guest attaches: getWebContentsId() now works and the test bridge can
    // see the webContentsId. But the guest document is NOT ready yet — Electron's
    // <webview>.loadURL throws "WebView must be attached to the DOM and the
    // dom-ready event emitted" until dom-ready fires.
    act(() => {
      webview.dispatchEvent(new Event("did-attach"));
    });

    // A navigation requested in the did-attach -> dom-ready window must be held,
    // not issued: calling loadURL here rejects and the navigation is lost,
    // stranding the guest at about:blank.
    act(() => {
      captured?.navigate("http://example.test/index.html");
    });
    expect(webview.loadURL).not.toHaveBeenCalled();

    // Once the document is ready, the held navigation replays exactly once.
    act(() => {
      webview.dispatchEvent(new Event("dom-ready"));
    });
    expect(webview.loadURL).toHaveBeenCalledTimes(1);
    expect(webview.loadURL).toHaveBeenCalledWith("http://example.test/index.html");
  });

  it("navigates immediately once the guest is dom-ready", () => {
    const webview = mountWebview();
    act(() => {
      webview.dispatchEvent(new Event("did-attach"));
      webview.dispatchEvent(new Event("dom-ready"));
    });

    act(() => {
      captured?.navigate("http://example.test/page.html");
    });
    expect(webview.loadURL).toHaveBeenCalledTimes(1);
    expect(webview.loadURL).toHaveBeenCalledWith("http://example.test/page.html");
  });

  it("re-waits for dom-ready after the guest is re-attached", () => {
    const webview = mountWebview();
    // First guest reaches readiness and navigates fine.
    act(() => {
      webview.dispatchEvent(new Event("did-attach"));
      webview.dispatchEvent(new Event("dom-ready"));
    });
    act(() => {
      captured?.navigate("http://example.test/first.html");
    });
    expect(webview.loadURL).toHaveBeenCalledTimes(1);

    // The guest is recreated: did-attach fires again, but the new guest's
    // document is not ready yet. A navigation now must be held until the new
    // guest fires dom-ready — not issued against the previous guest's readiness.
    act(() => {
      webview.dispatchEvent(new Event("did-attach"));
    });
    act(() => {
      captured?.navigate("http://example.test/second.html");
    });
    expect(webview.loadURL).toHaveBeenCalledTimes(1);

    act(() => {
      webview.dispatchEvent(new Event("dom-ready"));
    });
    expect(webview.loadURL).toHaveBeenCalledTimes(2);
    expect(webview.loadURL).toHaveBeenLastCalledWith("http://example.test/second.html");
  });
});
