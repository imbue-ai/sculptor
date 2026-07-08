import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { createStore } from "jotai";
import type { ComponentProps } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ElementIds } from "~/api";
import { renderWithProviders } from "~/common/testUtils.tsx";

import { keepNewWorkspaceModalOpenAtom } from "./newWorkspaceAtoms.ts";
import { NewWorkspaceForm } from "./NewWorkspaceForm.tsx";

// What is under test is the form's own behavior — seeding, submit, and the
// post-create callbacks — so everything that reaches the backend is stubbed at
// its module seam: the project fetches, the create flow, the per-repo branch
// info, the terminal-agent registrations, and the debounced branch-name
// preview/validation queries.
const { mockCreateWorkspace } = vi.hoisted(() => ({ mockCreateWorkspace: vi.fn() }));

vi.mock("~/api", async (importOriginal) => {
  const original = await importOriginal();
  return {
    ...(original as object),
    getActiveProjects: vi.fn(async () => ({ data: [{ objectId: "p1", name: "Repo One" }] })),
    getMostRecentlyUsedProject: vi.fn(async () => ({ data: "p1" })),
    // The agent-type select re-checks pi availability on mount.
    getDependenciesStatus: vi.fn(async () => ({ data: undefined })),
  };
});

vi.mock("~/common/state/hooks/useCreateWorkspace.ts", () => ({
  useCreateWorkspace: (): { isCreating: boolean; createWorkspace: typeof mockCreateWorkspace } => ({
    isCreating: false,
    createWorkspace: mockCreateWorkspace,
  }),
}));

vi.mock("~/common/state/hooks/useRepoInfo.ts", () => ({
  useRepoInfo: (): unknown => ({
    repoInfo: { currentBranch: "main", recentBranches: ["main"] },
    fetchRepoInfo: vi.fn(),
    fetchCurrentBranch: vi.fn(),
  }),
}));

vi.mock("~/common/state/hooks/useTerminalAgentRegistrations.ts", () => ({
  useTerminalAgentRegistrations: (): unknown => ({ registrations: [], refetch: vi.fn() }),
}));

vi.mock("~/components/newWorkspace/hooks/useBranchNamePreview.ts", () => ({
  useBranchNamePreview: (): unknown => ({
    preview: "sculptor/test-branch",
    displayedValue: "sculptor/test-branch",
    isLoading: false,
    status: "available",
  }),
}));

type FormProps = ComponentProps<typeof NewWorkspaceForm>;

const renderForm = (
  props: Partial<FormProps> = {},
  options: { keepOpen?: boolean } = {},
): ReturnType<typeof renderWithProviders> => {
  const store = createStore();
  if (options.keepOpen) {
    store.set(keepNewWorkspaceModalOpenAtom, true);
  }
  return renderWithProviders(<NewWorkspaceForm onCreated={vi.fn()} {...props} />, { store });
};

// The Create button stays disabled until the (mocked) project fetch resolves a
// selection, so wait for it to enable before clicking.
const clickCreate = async (): Promise<void> => {
  const button = screen.getByTestId(ElementIds.NEW_WORKSPACE_CREATE_BUTTON);
  await waitFor(() => expect(button).toBeEnabled());
  fireEvent.click(button);
};

describe("NewWorkspaceForm", () => {
  beforeEach(() => {
    mockCreateWorkspace.mockResolvedValue({ ok: true, workspaceId: "w1" });
  });

  // vitest runs with `globals: false`, so RTL's automatic post-test cleanup
  // isn't registered — do it explicitly. keepNewWorkspaceModalOpenAtom persists
  // to localStorage, so wipe that too.
  afterEach(() => {
    cleanup();
    mockCreateWorkspace.mockReset();
    window.localStorage.clear();
  });

  it("seeds the title and prompt fields from the open request", () => {
    renderForm({ initialTitle: "Fix the bug", initialPrompt: "Please fix it" });

    expect(screen.getByTestId(ElementIds.WORKSPACE_NAME_INPUT)).toHaveValue("Fix the bug");
    expect(screen.getByTestId(ElementIds.NEW_WORKSPACE_PROMPT_TEXTAREA)).toHaveValue("Please fix it");
  });

  it("reports a successful create to onWorkspaceCreated, then closes via onCreated", async () => {
    const onWorkspaceCreated = vi.fn();
    const onCreated = vi.fn();
    renderForm({ onWorkspaceCreated, onCreated });

    await clickCreate();

    await waitFor(() => expect(onCreated).toHaveBeenCalledTimes(1));
    expect(onWorkspaceCreated).toHaveBeenCalledExactlyOnceWith("w1");
    // The open request's own callback observes the create before the form
    // reports completion to its host.
    expect(onWorkspaceCreated.mock.invocationCallOrder[0]).toBeLessThan(onCreated.mock.invocationCallOrder[0]);
  });

  it("contains a throwing onWorkspaceCreated so the post-create flow still runs", async () => {
    const onWorkspaceCreated = vi.fn(() => {
      throw new Error("plugin exploded");
    });
    const onCreated = vi.fn();
    // The form logs the contained throw; keep the test output clean.
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
    try {
      renderForm({ onWorkspaceCreated, onCreated });

      await clickCreate();

      await waitFor(() => expect(onCreated).toHaveBeenCalledTimes(1));
      expect(onWorkspaceCreated).toHaveBeenCalledExactlyOnceWith("w1");
    } finally {
      consoleError.mockRestore();
    }
  });

  it("re-seeds the title and prompt after a keep-open create", async () => {
    const onWorkspaceCreated = vi.fn();
    const onCreated = vi.fn();
    renderForm(
      { initialTitle: "Fix the bug", initialPrompt: "Please fix it", onWorkspaceCreated, onCreated },
      { keepOpen: true },
    );

    // The user repurposes the seeded dialog for this one create...
    const titleInput = screen.getByTestId(ElementIds.WORKSPACE_NAME_INPUT);
    const promptTextarea = screen.getByTestId(ElementIds.NEW_WORKSPACE_PROMPT_TEXTAREA);
    fireEvent.change(titleInput, { target: { value: "Edited title" } });
    fireEvent.change(promptTextarea, { target: { value: "Edited prompt" } });

    await clickCreate();

    // ...the create still reports to the open request's callback, and the
    // fields return to the request's seeds (not blank) so the still-open
    // dialog keeps saying what the request is.
    await waitFor(() => expect(onWorkspaceCreated).toHaveBeenCalledExactlyOnceWith("w1"));
    expect(onCreated).not.toHaveBeenCalled();
    await waitFor(() => expect(titleInput).toHaveValue("Fix the bug"));
    expect(promptTextarea).toHaveValue("Please fix it");
  });
});
