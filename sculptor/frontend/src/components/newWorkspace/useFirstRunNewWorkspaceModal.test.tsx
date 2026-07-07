import { act, cleanup } from "@testing-library/react";
import { createStore } from "jotai";
import { afterEach, describe, expect, it } from "vitest";

import type { Workspace } from "~/api";
import { workspaceAtomFamily, workspaceIdsAtom } from "~/common/state/atoms/workspaces.ts";
import { renderWithProviders } from "~/common/testUtils.tsx";

import { HOME_PROMPT_PREFILL } from "./homePromptPrefill.ts";
import { newWorkspaceModalAtom } from "./newWorkspaceAtoms.ts";
import { useFirstRunNewWorkspaceModal } from "./useFirstRunNewWorkspaceModal.ts";

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

    expect(store.get(newWorkspaceModalAtom)).toEqual({ open: true, initialPrompt: HOME_PROMPT_PREFILL });
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
    expect(store.get(newWorkspaceModalAtom)).toEqual({ open: true, initialPrompt: HOME_PROMPT_PREFILL });
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
});
