import { QueryClientProvider } from "@tanstack/react-query";
import { cleanup, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createStore } from "jotai";
import type { ReactElement } from "react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { ElementIds, type Project, type Workspace } from "~/api";
import { queryClient } from "~/common/queryClient";
import { projectAtomFamily, projectIdsAtom } from "~/common/state/atoms/projects.ts";
import { workspaceAtomFamily, workspaceIdsAtom } from "~/common/state/atoms/workspaces.ts";
import { renderWithProviders } from "~/common/testUtils.tsx";

import { WorkspaceSidebar } from "./WorkspaceSidebar.tsx";

const Sidebar = (): ReactElement => (
  <QueryClientProvider client={queryClient}>
    <WorkspaceSidebar />
  </QueryClientProvider>
);

const seedWorkspaces = (store: ReturnType<typeof createStore>, ids: ReadonlyArray<string>): void => {
  for (const id of ids) {
    store.set(workspaceAtomFamily(id), {
      objectId: id,
      description: `ws-${id}`,
      projectId: "p1",
    } as unknown as Workspace);
  }
  store.set(workspaceIdsAtom, [...ids]);
};

const seedProject = (store: ReturnType<typeof createStore>, id: string): void => {
  store.set(projectAtomFamily(id), { objectId: id, name: `repo-${id}` } as unknown as Project);
  store.set(projectIdsAtom, [id]);
};

describe("WorkspaceSidebar nav buttons", () => {
  let store: ReturnType<typeof createStore>;

  beforeEach(() => {
    store = createStore();
  });

  // vitest runs with `globals: false`, so RTL's automatic post-test cleanup
  // isn't registered — do it explicitly so each render starts from a fresh DOM.
  // The shared TanStack client is a process-wide singleton, so wipe its cache too
  // (a rendered SidebarRepoGroup mounts query-backed hooks) or cached state leaks
  // into later tests and makes their order matter.
  afterEach(() => {
    cleanup();
    queryClient.clear();
  });

  it("keeps Search and New Workspace enabled when the workspace list is empty", () => {
    // An empty (but loaded) list — the first-run state. The new-workspace
    // dialog and the command palette are reachable here, so the buttons stay
    // live as the reopen paths for the auto-opened dialog.
    store.set(workspaceIdsAtom, []);
    renderWithProviders(<Sidebar />, { store });

    expect(screen.getByTestId(ElementIds.SIDEBAR_CMDK_LINK)).toBeEnabled();
    expect(screen.getByTestId(ElementIds.SIDEBAR_NEW_WORKSPACE_BUTTON)).toBeEnabled();
  });

  it("keeps Search and New Workspace enabled once a workspace exists", () => {
    seedWorkspaces(store, ["w1"]);
    renderWithProviders(<Sidebar />, { store });

    expect(screen.getByTestId(ElementIds.SIDEBAR_CMDK_LINK)).toBeEnabled();
    expect(screen.getByTestId(ElementIds.SIDEBAR_NEW_WORKSPACE_BUTTON)).toBeEnabled();
  });

  it("keeps the Add repo button enabled even when the workspace list is empty", () => {
    // Registering a repo is the natural first-run action, so it is live like
    // every other nav button.
    store.set(workspaceIdsAtom, []);
    renderWithProviders(<Sidebar />, { store });

    expect(screen.getByTestId(ElementIds.SIDEBAR_ADD_REPO_BUTTON)).not.toBeDisabled();
  });
});

describe("WorkspaceSidebar repo groups", () => {
  let store: ReturnType<typeof createStore>;

  beforeEach(() => {
    store = createStore();
  });

  afterEach(() => {
    cleanup();
    queryClient.clear();
  });

  it("renders a repo with no workspaces as a group with a hint and live per-repo actions", () => {
    // A registered repo before its first workspace exists must still appear in
    // the sidebar (otherwise a just-added repo silently vanishes). Its "+" and
    // settings actions work here too: the new-workspace dialog host (AppShell)
    // is mounted on every route, so the "+"'s dialog fallback and error toast
    // have somewhere to land even with zero workspaces.
    seedProject(store, "p1");
    store.set(workspaceIdsAtom, []);
    renderWithProviders(<Sidebar />, { store });

    expect(screen.getByTestId(ElementIds.SIDEBAR_REPO_GROUP)).toBeVisible();
    expect(screen.getByTestId(ElementIds.SIDEBAR_NO_WORKSPACES_HINT)).toBeVisible();
    expect(screen.getByTestId(ElementIds.SIDEBAR_REPO_ADD_WORKSPACE)).toBeVisible();
  });

  it("shows the per-repo actions once a workspace exists", () => {
    seedProject(store, "p1");
    seedWorkspaces(store, ["w1"]);
    renderWithProviders(<Sidebar />, { store });

    expect(screen.getByTestId(ElementIds.SIDEBAR_REPO_ADD_WORKSPACE)).toBeVisible();
  });

  it("enters inline rename mode when a workspace row is double-clicked", async () => {
    // user.dblClick fires the real click → click → dblclick sequence, so the
    // clicks that precede a dblclick are exercised and shown not to block the row
    // from entering rename mode.
    const user = userEvent.setup();
    seedProject(store, "p1");
    seedWorkspaces(store, ["w1"]);
    renderWithProviders(<Sidebar />, { store });

    expect(screen.queryByTestId(ElementIds.INLINE_RENAME_INPUT)).toBeNull();

    await user.dblClick(screen.getByTestId(ElementIds.SIDEBAR_WORKSPACE_ROW));

    expect(await screen.findByTestId(ElementIds.INLINE_RENAME_INPUT)).toBeVisible();
  });
});
