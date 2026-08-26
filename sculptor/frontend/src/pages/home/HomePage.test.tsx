import { act, cleanup } from "@testing-library/react";
import { createStore } from "jotai";
import type { ReactElement } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Workspace } from "~/api";
import { updateWorkspacesAtom, workspaceIdsAtom } from "~/common/state/atoms/workspaces.ts";
import { renderWithProviders } from "~/common/testUtils.tsx";
import { HOME_PROMPT_PREFILL } from "~/components/newWorkspace/homePromptPrefill.ts";
import { newWorkspaceModalAtom } from "~/components/newWorkspace/newWorkspaceAtoms.ts";

import { HomePage } from "./HomePage.tsx";

// The home views pull in router hooks and backend queries; the first-run
// auto-open effect is what is under test, so stub the content out.
vi.mock("./RecentWorkspacesHomeView.tsx", () => ({
  RecentWorkspacesHomeView: (): ReactElement => <div data-testid="stub-home-view" />,
}));
vi.mock("./HomeViewSwitcher.tsx", () => ({
  HomeViewSwitcher: (): ReactElement => <div data-testid="stub-view-switcher" />,
}));

const mockWorkspace = (overrides: Partial<Workspace> & Pick<Workspace, "objectId">): Workspace =>
  ({
    projectId: "p1",
    organizationReference: "org-1",
    description: `ws-${overrides.objectId}`,
    initializationStrategy: "CLONE",
    isOpen: true,
    isDeleted: false,
    ...overrides,
  }) as Workspace;

describe("HomePage first-run auto-open", () => {
  // vitest runs with `globals: false`, so RTL's automatic post-test cleanup
  // isn't registered — do it explicitly so each render starts from a fresh DOM.
  afterEach(() => {
    cleanup();
  });

  it("offers the create dialog with the onboarding prompt when the boot snapshot is empty", () => {
    const store = createStore();
    store.set(updateWorkspacesAtom, []);
    renderWithProviders(<HomePage />, { store });

    expect(store.get(newWorkspaceModalAtom)).toEqual({ open: true, initialPrompt: HOME_PROMPT_PREFILL });
  });

  it("does not offer while the workspace list is still loading", () => {
    const store = createStore();
    expect(store.get(workspaceIdsAtom)).toBeUndefined();
    renderWithProviders(<HomePage />, { store });

    expect(store.get(newWorkspaceModalAtom)).toEqual({ open: false });
  });

  it("does not offer when workspaces exist", () => {
    const store = createStore();
    store.set(updateWorkspacesAtom, [mockWorkspace({ objectId: "w1" })]);
    renderWithProviders(<HomePage />, { store });

    expect(store.get(newWorkspaceModalAtom)).toEqual({ open: false });
  });

  it("does not offer after the last workspace is deleted mid-session", () => {
    // Deleting the last workspace lands the user on an empty Home. The offer
    // is an onboarding affordance for a boot with zero workspaces — popping
    // the dialog over a deliberate delete would fight the user's intent.
    const store = createStore();
    store.set(updateWorkspacesAtom, [mockWorkspace({ objectId: "w1" })]);
    renderWithProviders(<HomePage />, { store });

    act(() => {
      store.set(updateWorkspacesAtom, [mockWorkspace({ objectId: "w1", isDeleted: true })]);
    });
    expect(store.get(newWorkspaceModalAtom)).toEqual({ open: false });
  });

  it("never clobbers a dialog the user already opened", () => {
    // An open request made during the load window (Cmd/Meta+T, a repo "+"
    // fallback with a preset repo) must survive the empty snapshot landing:
    // replacing it would drop the preset repo, remount the form, and discard
    // anything the user typed.
    const store = createStore();
    store.set(newWorkspaceModalAtom, { open: true, presetProjectId: "p1" });
    renderWithProviders(<HomePage />, { store });

    act(() => {
      store.set(updateWorkspacesAtom, []);
    });
    expect(store.get(newWorkspaceModalAtom)).toEqual({ open: true, presetProjectId: "p1" });
  });
});
