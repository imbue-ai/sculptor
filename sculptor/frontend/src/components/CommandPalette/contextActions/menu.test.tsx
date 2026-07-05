import { ContextMenu, DropdownMenu, Theme } from "@radix-ui/themes";
import { cleanup, render, screen } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import type { ReactElement } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ElementIds, type Workspace } from "../../../api";
import type { OpenInRuntime } from "./menu.tsx";
import { WorkspaceContextMenuContent, WorkspaceDropdownMenuContent } from "./menu.tsx";
import type { WorkspaceAction } from "./types.ts";

afterEach(() => {
  cleanup();
});

const fakeWorkspace = (id: string): Workspace =>
  ({ objectId: id, description: `ws-${id}`, sourceBranch: "main" }) as unknown as Workspace;

// A minimal action set mirroring `buildWorkspaceActions` shape: the copy
// group is injected relative to the `rename` action, so it must be present.
const makeActions = (): ReadonlyArray<WorkspaceAction> => [
  { id: "commit", title: "Commit changes", perform: vi.fn() },
  { id: "open_pr", title: "Open pull request", perform: vi.fn() },
  { id: "rename", title: "Rename workspace", perform: vi.fn() },
  { id: "delete", title: "Delete workspace", destructive: true, perform: vi.fn() },
];

const openInRuntime: OpenInRuntime = {
  openInApp: vi.fn(),
  // Force the "Open in..." submenu off in tests (no electron), so the copy
  // group is the meaningful reconciliation assertion.
  canOpenInOS: () => false,
  isMacUi: () => false,
};

const renderInDropdown = (ui: ReactElement): void => {
  const store = createStore();
  render(
    <Provider store={store}>
      <Theme>
        <DropdownMenu.Root open>
          <DropdownMenu.Trigger>
            <button type="button">menu</button>
          </DropdownMenu.Trigger>
          {ui}
        </DropdownMenu.Root>
      </Theme>
    </Provider>,
  );
};

const renderInContextMenu = (ui: ReactElement): void => {
  const store = createStore();
  render(
    <Provider store={store}>
      <Theme>
        <ContextMenu.Root open>{ui}</ContextMenu.Root>
      </Theme>
    </Provider>,
  );
};

// Radix menus can render their content more than once in jsdom (a visible
// copy plus a measurement/a11y copy), so assert presence via *AllBy* with a
// non-zero count rather than the single-match getBy*.
const expectPresent = (testId: string): void => {
  expect(screen.getAllByTestId(testId).length).toBeGreaterThan(0);
};

describe("WorkspaceDropdownMenuContent", () => {
  it("includes the copy/diagnostics group the right-click menu has (parity)", () => {
    renderInDropdown(
      <WorkspaceDropdownMenuContent
        actions={makeActions()}
        workspace={fakeWorkspace("w1")}
        destructiveColor="red"
        openInRuntime={openInRuntime}
      />,
    );
    // The "..." dropdown must surface the same copy-name / copy-branch /
    // diagnostics entries the right-click context menu injects.
    expectPresent(ElementIds.TAB_CONTEXT_MENU_COPY_WORKSPACE_NAME);
    expectPresent(ElementIds.TAB_CONTEXT_MENU_COPY_BRANCH);
    expectPresent(ElementIds.TAB_CONTEXT_MENU_DIAGNOSTICS);
  });

  it("renders the descriptor actions", () => {
    renderInDropdown(
      <WorkspaceDropdownMenuContent
        actions={makeActions()}
        workspace={fakeWorkspace("w2")}
        destructiveColor="red"
        openInRuntime={openInRuntime}
      />,
    );
    expect(screen.getAllByText("Rename workspace").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Delete workspace").length).toBeGreaterThan(0);
  });
});

describe("WorkspaceContextMenuContent", () => {
  it("still includes the copy/diagnostics group", () => {
    renderInContextMenu(
      <WorkspaceContextMenuContent
        actions={makeActions()}
        workspace={fakeWorkspace("w3")}
        destructiveColor="red"
        openInRuntime={openInRuntime}
      />,
    );
    expectPresent(ElementIds.TAB_CONTEXT_MENU_COPY_WORKSPACE_NAME);
    expectPresent(ElementIds.TAB_CONTEXT_MENU_COPY_BRANCH);
  });
});
