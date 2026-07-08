import { cleanup, screen } from "@testing-library/react";
import { createStore } from "jotai";
import type { ReactElement } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ElementIds } from "~/api";
import { renderWithProviders } from "~/common/testUtils.tsx";

import { newWorkspaceModalAtom } from "./newWorkspaceAtoms.ts";
import { NewWorkspaceModal } from "./NewWorkspaceModal.tsx";

// The real form pulls in project queries and creation hooks; the modal's
// open/close contract is what is under test, so stub the form out — surfacing
// the props the modal forwards so the seed passthrough is assertable.
vi.mock("~/components/newWorkspace/NewWorkspaceForm.tsx", () => ({
  NewWorkspaceForm: ({ initialPrompt }: { initialPrompt?: string }): ReactElement => (
    <div data-testid="stub-form" data-initial-prompt={initialPrompt} />
  ),
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

  it("forwards the open request's initial prompt to the form", () => {
    // The home page's first-run auto-open seeds the onboarding prompt through
    // the open request; the modal must hand it to the form untouched.
    const store = createStore();
    store.set(newWorkspaceModalAtom, { open: true, initialPrompt: "/sculptor:help hello" });
    renderWithProviders(<NewWorkspaceModal />, { store });
    expect(screen.getByTestId("stub-form").getAttribute("data-initial-prompt")).toBe("/sculptor:help hello");
  });

  it("renders an explicit open as a modal dialog (with overlay)", () => {
    const store = createStore();
    store.set(newWorkspaceModalAtom, { open: true });
    renderWithProviders(<NewWorkspaceModal />, { store });
    expect(screen.getByTestId(ElementIds.PALETTE_DIALOG_OVERLAY)).toBeTruthy();
  });

  it("renders a first-run open non-modally (no overlay)", () => {
    // The auto-open is an offer, not a gate: no overlay, background stays
    // interactive, so a dialog the user never asked for can't block a click.
    const store = createStore();
    store.set(newWorkspaceModalAtom, { open: true, firstRun: true });
    renderWithProviders(<NewWorkspaceModal />, { store });
    expect(screen.getByTestId(ElementIds.NEW_WORKSPACE_DIALOG)).toBeTruthy();
    expect(screen.queryByTestId(ElementIds.PALETTE_DIALOG_OVERLAY)).toBeNull();
  });
});
