import { Theme } from "@radix-ui/themes";
import { cleanup, render, screen } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ElementIds } from "~/api";

import { type BrowserViewStatus, browserViewStatusAtomFamily } from "./browser/browserViewRegistry";
import { BrowserPanel } from "./BrowserPanel";

vi.mock("~/electron/utils", () => ({
  isElectron: vi.fn(),
}));

// The Electron panel reads the active workspace's id from the router; pin it.
vi.mock("~/common/hooks/navigation", async (importOriginal) => ({
  ...(await importOriginal<object>()),
  useWorkspacePageParams: (): { workspaceID: string } => ({ workspaceID: WORKSPACE_ID }),
}));

// The placement hook drives the <webview> bounds via refs/ResizeObserver, which
// is irrelevant to the toolbar's rendered output; stub it so the panel renders
// without a layout environment.
vi.mock("./browser/useBrowserPanelPlacement", () => ({
  useBrowserPanelPlacement: (): void => {},
}));

const WORKSPACE_ID = "ws-browser-test";

const STATUS_DEFAULT: BrowserViewStatus = {
  currentUrl: "",
  canGoBack: false,
  canGoForward: false,
  isLoading: false,
  webContentsId: null,
};

const renderBrowserPanel = (status: Partial<BrowserViewStatus> = {}): void => {
  const store = createStore();
  store.set(browserViewStatusAtomFamily(WORKSPACE_ID), { ...STATUS_DEFAULT, ...status });
  const Wrapper = ({ children }: { children: ReactNode }): ReactElement => (
    <Provider store={store}>
      <Theme>{children}</Theme>
    </Provider>
  );
  render(<BrowserPanel />, { wrapper: Wrapper });
};

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("BrowserPanel", () => {
  it("renders the web-mode placeholder when running outside Electron", async () => {
    const { isElectron } = await import("~/electron/utils");
    (isElectron as ReturnType<typeof vi.fn>).mockReturnValue(false);

    renderBrowserPanel();

    expect(screen.getByTestId(ElementIds.BROWSER_WEB_MODE_PLACEHOLDER)).toBeInTheDocument();
    expect(screen.getByText(/desktop app/i)).toBeInTheDocument();
  });

  it("surfaces the committed webview status on the panel for integration tests", async () => {
    // The page object gates on these production-truth attributes instead of a
    // focus-coupled global bridge or a guest document.location round-trip.
    const { isElectron } = await import("~/electron/utils");
    (isElectron as ReturnType<typeof vi.fn>).mockReturnValue(true);

    renderBrowserPanel({ webContentsId: 7, currentUrl: "http://example.test/page.html" });

    const panel = screen.getByTestId(ElementIds.BROWSER_PANEL);
    expect(panel).toHaveAttribute("data-webview-content-id", "7");
    expect(panel).toHaveAttribute("data-webview-current-url", "http://example.test/page.html");
  });

  it("omits the content id until the guest has attached", async () => {
    const { isElectron } = await import("~/electron/utils");
    (isElectron as ReturnType<typeof vi.fn>).mockReturnValue(true);

    renderBrowserPanel({ webContentsId: null });

    expect(screen.getByTestId(ElementIds.BROWSER_PANEL)).not.toHaveAttribute("data-webview-content-id");
  });
});
