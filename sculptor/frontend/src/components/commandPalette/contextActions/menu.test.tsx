import { ContextMenu, DropdownMenu, Theme } from "@radix-ui/themes";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createStore, Provider } from "jotai";
import type { ReactElement } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ElementIds, type Workspace, WorkspaceInitializationStrategy } from "../../../api";
import { workspaceBranchAtomFamily } from "../../../common/state/atoms/workspaceBranch.ts";
import { workspaceJjStateAtomFamily } from "../../../common/state/atoms/workspaceJjState.ts";
import type { OpenInRuntime } from "./menu.tsx";
import { WorkspaceContextMenuContent, WorkspaceDropdownMenuContent } from "./menu.tsx";
import type { WorkspaceAction } from "./types/contextActions.ts";

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

const renderInDropdown = (ui: ReactElement, store = createStore()): void => {
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

describe("Copy branch", () => {
  it("copies the workspace's live branch", async () => {
    const user = userEvent.setup();
    const store = createStore();
    store.set(workspaceBranchAtomFamily("w4"), { currentBranch: "dev/feature", workspaceId: "w4" });
    renderInDropdown(
      <WorkspaceDropdownMenuContent
        actions={makeActions()}
        workspace={fakeWorkspace("w4")}
        destructiveColor="red"
        openInRuntime={openInRuntime}
      />,
      store,
    );

    await user.click(screen.getAllByTestId(ElementIds.TAB_CONTEXT_MENU_COPY_BRANCH)[0]);

    expect(await navigator.clipboard.readText()).toBe("dev/feature");
  });

  it("does not offer the branch the workspace was created from while its own branch loads", () => {
    renderInDropdown(
      <WorkspaceDropdownMenuContent
        actions={makeActions()}
        workspace={fakeWorkspace("w5")}
        destructiveColor="red"
        openInRuntime={openInRuntime}
      />,
    );

    expect(screen.getAllByTestId(ElementIds.TAB_CONTEXT_MENU_COPY_BRANCH)[0].getAttribute("aria-disabled")).toBe(
      "true",
    );
  });
});

describe("Copy bookmark and change id", () => {
  const CHANGE_ID = "kxqpmzvyrstuwlnokxqpmzvyrstuwlno";

  const fakeJjWorkspace = (id: string): Workspace =>
    ({
      objectId: id,
      description: `ws-${id}`,
      initializationStrategy: WorkspaceInitializationStrategy.JJ_WORKSPACE,
    }) as unknown as Workspace;

  const storeWithJjState = (id: string, primaryBookmark: string | null): ReturnType<typeof createStore> => {
    const store = createStore();
    store.set(workspaceJjStateAtomFamily(id), {
      workspaceId: id,
      workingCopyChangeId: CHANGE_ID,
      workingCopyChangeIdPrefixLength: 2,
      workingCopyDescription: "",
      isWorkingCopyEmpty: false,
      bookmarks: primaryBookmark === null ? [] : [primaryBookmark],
      primaryBookmark,
      unbookmarkedRevisionCount: 0,
      hasConflict: false,
      isDivergent: false,
      isWorkingCopyStale: false,
    });
    return store;
  };

  const renderJjMenu = (id: string, store: ReturnType<typeof createStore>): void => {
    renderInDropdown(
      <WorkspaceDropdownMenuContent
        actions={makeActions()}
        workspace={fakeJjWorkspace(id)}
        destructiveColor="red"
        openInRuntime={openInRuntime}
      />,
      store,
    );
  };

  it("copies a jj workspace's primary bookmark in place of a branch", async () => {
    const user = userEvent.setup();
    renderJjMenu("w6", storeWithJjState("w6", "dev/feature"));

    const copyBookmark = screen.getAllByTestId(ElementIds.TAB_CONTEXT_MENU_COPY_BRANCH)[0];
    expect(copyBookmark.textContent).toContain("Copy bookmark");
    await user.click(copyBookmark);

    expect(await navigator.clipboard.readText()).toBe("dev/feature");
  });

  it("copies a jj workspace's change id", async () => {
    const user = userEvent.setup();
    renderJjMenu("w7", storeWithJjState("w7", "dev/feature"));

    await user.click(screen.getAllByText("Copy change id")[0]);

    expect(await navigator.clipboard.readText()).toBe(CHANGE_ID);
  });

  it("offers no bookmark to copy while a jj workspace has none", () => {
    renderJjMenu("w8", storeWithJjState("w8", null));

    expect(screen.getAllByTestId(ElementIds.TAB_CONTEXT_MENU_COPY_BRANCH)[0].getAttribute("aria-disabled")).toBe(
      "true",
    );
  });
});
