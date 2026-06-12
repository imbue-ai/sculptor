import { Theme } from "@radix-ui/themes";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createStore, Provider } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FileDropdownMenu } from "./FileDropdownMenu.tsx";
import type { FileContextMenuContext } from "./types.ts";

// useWorkspaceCodePath depends on react-router params, which aren't available
// in this unit-test context.
vi.mock("~/pages/workspace/hooks/useWorkspaceCodePath.ts", () => ({
  useWorkspaceCodePath: (): string => "/repo",
}));

// Force the OS-integration submenu to render regardless of the test host.
vi.mock("~/common/state/atoms/backendCapabilities.ts", () => ({
  getBackendCapabilities: (): { canOpenInOS: boolean } => ({ canOpenInOS: true }),
}));

const Wrapper = ({ children }: { children: ReactNode }): ReactElement => {
  const store = createStore();
  return (
    <Provider store={store}>
      <Theme>{children}</Theme>
    </Provider>
  );
};

const diffHeaderContext: FileContextMenuContext = {
  filePath: "src/app.py",
  isFolder: false,
  fileStatus: "M",
  isBinary: false,
  source: "diff-header",
};

afterEach(() => {
  cleanup();
});

describe("FileDropdownMenu", () => {
  it("opens with top-level actions and Copy path / Open in / Close submenus", async () => {
    const user = userEvent.setup();
    render(
      <FileDropdownMenu context={diffHeaderContext} workspaceId="ws-1">
        <button>menu</button>
      </FileDropdownMenu>,
      { wrapper: Wrapper },
    );

    await user.click(screen.getByRole("button", { name: "menu" }));

    expect(await screen.findByText("View file")).toBeInTheDocument();
    expect(screen.getByText("Copy path")).toBeInTheDocument();
    expect(screen.getByText("Open in")).toBeInTheDocument();
    expect(screen.getByText("Close")).toBeInTheDocument();

    // The long-tail actions live in submenus, not at the top level.
    expect(screen.queryByText("Copy file path")).not.toBeInTheDocument();
    expect(screen.queryByText("Open in default app")).not.toBeInTheDocument();
    expect(screen.queryByText("Close tab")).not.toBeInTheDocument();
  });

  it("reveals the copy actions when the Copy path submenu opens", async () => {
    const user = userEvent.setup();
    render(
      <FileDropdownMenu context={diffHeaderContext} workspaceId="ws-1">
        <button>menu</button>
      </FileDropdownMenu>,
      { wrapper: Wrapper },
    );

    await user.click(screen.getByRole("button", { name: "menu" }));
    await user.hover(await screen.findByText("Copy path"));

    expect(await screen.findByText("File path")).toBeInTheDocument();
    expect(screen.getByText("Relative path")).toBeInTheDocument();
  });

  it("reveals the tab actions when the Close submenu opens", async () => {
    const user = userEvent.setup();
    render(
      <FileDropdownMenu context={diffHeaderContext} workspaceId="ws-1">
        <button>menu</button>
      </FileDropdownMenu>,
      { wrapper: Wrapper },
    );

    await user.click(screen.getByRole("button", { name: "menu" }));
    await user.hover(await screen.findByText("Close"));

    expect(await screen.findByText("Close tab")).toBeInTheDocument();
    expect(screen.getByText("Close other tabs")).toBeInTheDocument();
    expect(screen.getByText("Close all")).toBeInTheDocument();
  });
});
