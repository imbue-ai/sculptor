import { cleanup, screen } from "@testing-library/react";
import { createStore } from "jotai";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ElementIds } from "~/api";
import { renderWithProviders } from "~/common/testUtils.tsx";

import { newWorkspaceModalAtom } from "./newWorkspaceAtoms.ts";
import { NewWorkspaceModal } from "./NewWorkspaceModal.tsx";

// The real form pulls in project queries and creation hooks; the modal's
// open/close contract is what is under test, so stub the form out.
vi.mock("~/components/newWorkspace/NewWorkspaceForm.tsx", () => ({
  NewWorkspaceForm: (): null => null,
}));

describe("NewWorkspaceModal", () => {
  // vitest runs with `globals: false`, so RTL's automatic post-test cleanup
  // isn't registered — do it explicitly so each render starts from a fresh DOM.
  afterEach(() => {
    cleanup();
  });

  it("renders nothing while the atom holds no open request", () => {
    const store = createStore();
    renderWithProviders(<NewWorkspaceModal />, { store });
    expect(screen.queryByTestId(ElementIds.NEW_WORKSPACE_DIALOG)).toBeNull();
  });

  it("renders the dialog for an open request", () => {
    const store = createStore();
    store.set(newWorkspaceModalAtom, { open: true });
    renderWithProviders(<NewWorkspaceModal />, { store });
    expect(screen.getByTestId(ElementIds.NEW_WORKSPACE_DIALOG)).toBeTruthy();
  });

  it("closes a stale open request when the host unmounts", () => {
    // The modal's only mount is AppShell, which unmounts when the first-run
    // page takes over. An open request set just before that swap must die with
    // the host — otherwise it survives invisibly in the store and pops the
    // dialog (overlay and all) over the first workspace created afterwards.
    const store = createStore();
    store.set(newWorkspaceModalAtom, { open: true });
    const { unmount } = renderWithProviders(<NewWorkspaceModal />, { store });
    expect(screen.getByTestId(ElementIds.NEW_WORKSPACE_DIALOG)).toBeTruthy();

    unmount();
    expect(store.get(newWorkspaceModalAtom)).toEqual({ open: false });
  });
});
