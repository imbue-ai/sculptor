import { act, cleanup } from "@testing-library/react";
import { createStore } from "jotai";
import { afterEach, describe, expect, it } from "vitest";

import type { Workspace } from "~/api";
import { workspaceAtomFamily, workspaceIdsAtom } from "~/common/state/atoms/workspaces.ts";
import { renderWithProviders } from "~/common/testUtils.tsx";

import { HOME_PROMPT_PREFILL } from "./homePromptPrefill.ts";
import { newWorkspaceModalAtom } from "./newWorkspaceAtoms.ts";
import { useFirstRunNewWorkspaceModal } from "./useFirstRunNewWorkspaceModal.ts";

const FIRST_RUN_OPEN_STATE = { open: true, initialPrompt: HOME_PROMPT_PREFILL, firstRun: true };

const HookHost = (): null => {
  useFirstRunNewWorkspaceModal();
  return null;
};

describe("useFirstRunNewWorkspaceModal", () => {
  // vitest runs with `globals: false`, so RTL's automatic post-test cleanup
  // isn't registered — do it explicitly so each render starts from a fresh DOM.
  afterEach(() => {
    cleanup();
  });

  it("opens the dialog with the onboarding prompt when the list is empty", () => {
    const store = createStore();
    store.set(workspaceIdsAtom, []);
    renderWithProviders(<HookHost />, { store });

    expect(store.get(newWorkspaceModalAtom)).toEqual(FIRST_RUN_OPEN_STATE);
  });

  it("does not open while the workspace list is still loading", () => {
    const store = createStore();
    expect(store.get(workspaceIdsAtom)).toBeUndefined();
    renderWithProviders(<HookHost />, { store });

    expect(store.get(newWorkspaceModalAtom)).toEqual({ open: false });
  });

  it("opens when the list settles empty after mount", () => {
    const store = createStore();
    renderWithProviders(<HookHost />, { store });
    expect(store.get(newWorkspaceModalAtom)).toEqual({ open: false });

    act(() => {
      store.set(workspaceIdsAtom, []);
    });
    expect(store.get(newWorkspaceModalAtom)).toEqual(FIRST_RUN_OPEN_STATE);
  });

  it("stays closed when workspaces exist", () => {
    const store = createStore();
    store.set(workspaceAtomFamily("w1"), {
      objectId: "w1",
      description: "ws-w1",
      projectId: "p1",
    } as unknown as Workspace);
    store.set(workspaceIdsAtom, ["w1"]);
    renderWithProviders(<HookHost />, { store });

    expect(store.get(newWorkspaceModalAtom)).toEqual({ open: false });
  });

  it("closes a still-first-run open when the host unmounts", () => {
    // Leaving Home retires the auto-open with it — the dialog is Home's
    // empty-state content, not a global popup.
    const store = createStore();
    store.set(workspaceIdsAtom, []);
    const { unmount } = renderWithProviders(<HookHost />, { store });
    expect(store.get(newWorkspaceModalAtom)).toEqual(FIRST_RUN_OPEN_STATE);

    unmount();
    expect(store.get(newWorkspaceModalAtom)).toEqual({ open: false });
  });

  it("leaves an explicit open request alone on unmount", () => {
    const store = createStore();
    store.set(workspaceIdsAtom, []);
    const { unmount } = renderWithProviders(<HookHost />, { store });

    // The user reopened the dialog explicitly (no firstRun marker) after the
    // auto-open — e.g. via the sidebar button.
    act(() => {
      store.set(newWorkspaceModalAtom, { open: true });
    });

    unmount();
    expect(store.get(newWorkspaceModalAtom)).toEqual({ open: true });
  });

  it("does not close the dialog when the first workspace arrives while it is open", () => {
    // A keep-open multi-create or a CLI-created workspace flips the list
    // non-empty mid-form; the dialog must not vanish under the user.
    const store = createStore();
    store.set(workspaceIdsAtom, []);
    renderWithProviders(<HookHost />, { store });
    expect(store.get(newWorkspaceModalAtom)).toEqual(FIRST_RUN_OPEN_STATE);

    act(() => {
      store.set(workspaceAtomFamily("w1"), {
        objectId: "w1",
        description: "ws-w1",
        projectId: "p1",
      } as unknown as Workspace);
      store.set(workspaceIdsAtom, ["w1"]);
    });
    expect(store.get(newWorkspaceModalAtom)).toEqual(FIRST_RUN_OPEN_STATE);
  });
});
