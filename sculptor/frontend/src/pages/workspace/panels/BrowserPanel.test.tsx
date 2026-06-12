import { Theme } from "@radix-ui/themes";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ElementIds } from "~/api";

import { BrowserPanel } from "./BrowserPanel";

vi.mock("~/electron/utils", () => ({
  isElectron: vi.fn(),
}));

const renderBrowserPanel = (): void => {
  render(
    <Theme>
      <BrowserPanel />
    </Theme>,
  );
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
});
