import { cleanup, screen } from "@testing-library/react";
import { createStore } from "jotai";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ElementIds } from "~/api";
import { renderWithProviders } from "~/common/testUtils.tsx";

import { newWorkspaceModalAtom } from "./newWorkspaceAtoms.ts";
import { NewWorkspaceModal } from "./NewWorkspaceModal.tsx";

// The real form pulls in project queries and creation hooks; the modal's
// open/close contract and its prop pass-through are what is under test, so
// stub the form out but record the props it receives.
const { formProps } = vi.hoisted(() => ({ formProps: vi.fn() }));
vi.mock("~/components/newWorkspace/NewWorkspaceForm.tsx", () => ({
  NewWorkspaceForm: (props: Record<string, unknown>): null => {
    formProps(props);
    return null;
  },
}));

describe("NewWorkspaceModal", () => {
  // vitest runs with `globals: false`, so RTL's automatic post-test cleanup
  // isn't registered — do it explicitly so each render starts from a fresh DOM.
  afterEach(() => {
    cleanup();
    formProps.mockClear();
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

  it("passes the open request's seeds and create callback through to the form", () => {
    // A plugin's open request (via the SDK's useOpenNewWorkspaceModal) rides
    // this atom; the form only sees what the modal forwards.
    const store = createStore();
    const onWorkspaceCreated = vi.fn();
    store.set(newWorkspaceModalAtom, {
      open: true,
      initialTitle: "Fix the bug",
      initialPrompt: "Please fix it",
      initialBranchName: "fix/the-bug",
      onWorkspaceCreated,
    });
    renderWithProviders(<NewWorkspaceModal />, { store });

    expect(formProps).toHaveBeenCalledWith(
      expect.objectContaining({
        initialTitle: "Fix the bug",
        initialPrompt: "Please fix it",
        initialBranchName: "fix/the-bug",
        onWorkspaceCreated,
      }),
    );
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
