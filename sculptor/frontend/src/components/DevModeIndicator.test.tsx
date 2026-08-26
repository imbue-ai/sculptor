import { Theme } from "@radix-ui/themes";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { afterEach, describe, expect, it } from "vitest";

import { DevModeIndicator } from "./DevModeIndicator.tsx";

const Wrapper = ({ children }: { children: ReactNode }): ReactElement => <Theme>{children}</Theme>;

// The component reads `window.sculptor?.getDevInfo`; set a partial mock (only
// the method the component touches) to exercise the Electron path.
const mockGetDevInfo = (iconDataUrl: string | null): void => {
  (window as unknown as { sculptor?: { getDevInfo: () => Promise<unknown> } }).sculptor = {
    getDevInfo: (): Promise<unknown> => Promise.resolve({ label: "src", workspaceId: "ws-1", iconDataUrl }),
  };
};

afterEach(() => {
  cleanup();
  delete (window as unknown as { sculptor?: unknown }).sculptor;
});

describe("DevModeIndicator", () => {
  it("renders an icon (never a bare dot) in pure-browser dev", () => {
    // No Electron `window.sculptor` in jsdom, so this hits the browser fallback
    // (import.meta.env.DEV is true under vitest). The indicator must always be
    // an <img>, never the removed accent dot.
    render(<DevModeIndicator />, { wrapper: Wrapper });

    const img = screen.getByTestId("dev-mode-indicator").querySelector("img");
    expect(img).not.toBeNull();
    expect(img?.getAttribute("src")).toBeTruthy();
  });

  it("prefers the Electron-provided dock icon when one is available", async () => {
    const iconDataUrl = "data:image/png;base64,iVBORw0KGgo=";
    mockGetDevInfo(iconDataUrl);

    render(<DevModeIndicator />, { wrapper: Wrapper });

    await waitFor(() => {
      const img = screen.getByTestId("dev-mode-indicator").querySelector("img");
      expect(img?.getAttribute("src")).toBe(iconDataUrl);
    });
  });
});
