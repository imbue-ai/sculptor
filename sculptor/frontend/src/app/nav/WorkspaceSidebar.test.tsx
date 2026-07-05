import { QueryClientProvider } from "@tanstack/react-query";
import { cleanup, screen } from "@testing-library/react";
import { createStore } from "jotai";
import type { ReactElement } from "react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { ElementIds, type Workspace } from "~/api";
import { queryClient } from "~/common/queryClient";
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

describe("WorkspaceSidebar empty-state nav buttons", () => {
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

  it("disables Search and New Workspace when the workspace list is empty", () => {
    // An empty (but loaded) list — `isWorkspaceListEmptyAtom` reports true.
    store.set(workspaceIdsAtom, []);
    renderWithProviders(<Sidebar />, { store });

    expect(screen.getByTestId(ElementIds.SIDEBAR_CMDK_LINK)).toBeDisabled();
    expect(screen.getByTestId(ElementIds.SIDEBAR_NEW_WORKSPACE_BUTTON)).toBeDisabled();
  });

  it("enables Search and New Workspace once a workspace exists", () => {
    seedWorkspaces(store, ["w1"]);
    renderWithProviders(<Sidebar />, { store });

    expect(screen.getByTestId(ElementIds.SIDEBAR_CMDK_LINK)).not.toBeDisabled();
    expect(screen.getByTestId(ElementIds.SIDEBAR_NEW_WORKSPACE_BUTTON)).not.toBeDisabled();
  });
});
