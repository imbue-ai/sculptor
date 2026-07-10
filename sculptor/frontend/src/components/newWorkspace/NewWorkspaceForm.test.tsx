import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createStore } from "jotai";
import type { ComponentProps } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { DependenciesStatus, ModelOption, Project } from "~/api";
import { ElementIds, WorkspaceInitializationStrategy } from "~/api";
import { dependenciesStatusAtom } from "~/common/state/atoms/dependenciesStatus.ts";
import { updateProjectsAtom } from "~/common/state/atoms/projects.ts";
import { renderWithProviders } from "~/common/testUtils.tsx";
import { SettingsSection } from "~/pages/settings/sections.ts";

import {
  keepNewWorkspaceModalOpenAtom,
  lastWorkspaceCreationSettingsAtom,
  newWorkspaceDraftAtom,
} from "./newWorkspaceAtoms.ts";
import { NewWorkspaceForm } from "./NewWorkspaceForm.tsx";

// What is under test is the form's own behavior — seeding, submit, and the
// post-create callbacks — so everything that reaches the backend is stubbed at
// its module seam: the project fetches, the create flow, the per-repo branch
// info, the terminal-agent registrations, the debounced branch-name
// preview/validation queries, and the pi model catalog.
const { mockCreateWorkspace, mockUsePiModels } = vi.hoisted(() => ({
  mockCreateWorkspace: vi.fn(),
  mockUsePiModels: vi.fn(),
}));

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

// The host-side pi catalog. Mocked so the admission-rule tests can drive the
// three catalog states (resolving / populated / empty) the modal must handle.
vi.mock("~/common/state/hooks/usePiModels.ts", () => ({
  usePiModels: (): unknown => mockUsePiModels(),
}));

// Settings navigation is a route change; the CTA tests only assert the form
// asks for the right section.
const { mockOpenSettings } = vi.hoisted(() => ({ mockOpenSettings: vi.fn() }));
vi.mock("~/common/state/hooks/useOpenSettings.ts", () => ({
  useOpenSettings: (): unknown => mockOpenSettings,
}));

const PI_MODEL_DEFAULT: ModelOption = { provider: "anthropic", modelId: "sonnet", displayName: "Sonnet" };
const PI_MODEL_OTHER: ModelOption = { provider: "openai", modelId: "gpt", displayName: "GPT" };

// usePiModels' return shape, one factory per catalog state. Each returns a fresh
// object; a test hands one to `mockReturnValue` so the reference stays stable
// across renders.
const piModelsResolving = (): unknown => ({
  data: undefined,
  availableModels: [],
  defaultModel: null,
  isPending: true,
  isFetching: true,
  isError: false,
  error: null,
  refetch: vi.fn(),
});
const piModelsPopulated = (): unknown => ({
  data: { availableModels: [PI_MODEL_DEFAULT, PI_MODEL_OTHER], defaultModel: PI_MODEL_DEFAULT },
  availableModels: [PI_MODEL_DEFAULT, PI_MODEL_OTHER],
  defaultModel: PI_MODEL_DEFAULT,
  isPending: false,
  isFetching: false,
  isError: false,
  error: null,
  refetch: vi.fn(),
});
const piModelsEmpty = (): unknown => ({
  data: { availableModels: [], defaultModel: null },
  availableModels: [],
  defaultModel: null,
  isPending: false,
  isFetching: false,
  isError: false,
  error: null,
  refetch: vi.fn(),
});

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

// Honors the override argument the same way the real hook does (override wins
// over the auto preview), so a seeded or user-edited branch name is observable
// in the rendered field and in the create call's `branchName`.
vi.mock("~/components/newWorkspace/hooks/useBranchNamePreview.ts", () => ({
  useBranchNamePreview: ({ override }: { override: string | null }): unknown => ({
    preview: "sculptor/test-branch",
    displayedValue: override ?? "sculptor/test-branch",
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
  // The app keeps the projects atom populated before the modal can open. With
  // an empty store, the form's initial project load would look like a repo
  // just added through the Add Repository dialog, which the form answers by
  // auto-selecting it and resetting branch choices — clobbering mount-time
  // seeds. Pre-populate the store so the tests see the app's real conditions.
  store.set(updateProjectsAtom, [{ objectId: "p1", name: "Repo One" } as Project]);
  if (options.keepOpen) {
    store.set(keepNewWorkspaceModalOpenAtom, true);
  }
  return renderWithProviders(<NewWorkspaceForm onCreated={vi.fn()} onDismiss={vi.fn()} {...props} />, { store });
};

// Seed pi as the first-agent type via the last-create settings (pi availability
// fails open in the test, so the seed is honored) and start on the selected repo.
const renderPiForm = (props: Partial<FormProps> = {}): ReturnType<typeof renderWithProviders> => {
  const store = createStore();
  store.set(updateProjectsAtom, [{ objectId: "p1", name: "Repo One" } as Project]);
  store.set(lastWorkspaceCreationSettingsAtom, {
    projectId: "p1",
    agentType: "pi",
    initStrategy: WorkspaceInitializationStrategy.WORKTREE,
  });
  return renderWithProviders(<NewWorkspaceForm onCreated={vi.fn()} onDismiss={vi.fn()} {...props} />, { store });
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
    // Default the catalog to still-resolving; the Claude tests never read it, and
    // the pi tests override per case.
    mockUsePiModels.mockReturnValue(piModelsResolving());
  });

  // vitest runs with `globals: false`, so RTL's automatic post-test cleanup
  // isn't registered — do it explicitly. keepNewWorkspaceModalOpenAtom persists
  // to localStorage, so wipe that too.
  afterEach(() => {
    cleanup();
    mockCreateWorkspace.mockReset();
    mockUsePiModels.mockReset();
    window.localStorage.clear();
  });

  it("seeds the title and prompt fields from the open request", () => {
    renderForm({ initialTitle: "Fix the bug", initialPrompt: "Please fix it" });

    expect(screen.getByTestId(ElementIds.WORKSPACE_NAME_INPUT)).toHaveValue("Fix the bug");
    expect(screen.getByTestId(ElementIds.NEW_WORKSPACE_PROMPT_TEXTAREA)).toHaveValue("Please fix it");
  });

  it("seeds the branch-name field into override mode and creates with the seeded name", async () => {
    renderForm({ initialBranchName: "linear/scu-1-fix" });

    // The seed lands as a manual override, so the field shows it in place of
    // the auto preview.
    expect(screen.getByTestId(ElementIds.BRANCH_NAME_INPUT)).toHaveValue("linear/scu-1-fix");

    await clickCreate();

    await waitFor(() =>
      expect(mockCreateWorkspace).toHaveBeenCalledWith(expect.objectContaining({ branchName: "linear/scu-1-fix" })),
    );
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
      throw new Error("extension exploded");
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

  it("re-seeds the branch name after a keep-open create", async () => {
    renderForm({ initialBranchName: "linear/scu-1-fix" }, { keepOpen: true });

    // The user hand-edits the branch for this one create...
    const branchInput = screen.getByTestId(ElementIds.BRANCH_NAME_INPUT);
    fireEvent.change(branchInput, { target: { value: "custom/branch" } });

    await clickCreate();

    await waitFor(() =>
      expect(mockCreateWorkspace).toHaveBeenCalledWith(expect.objectContaining({ branchName: "custom/branch" })),
    );
    // ...and the still-open dialog returns to the request's seeded branch name
    // (not the auto preview).
    await waitFor(() => expect(branchInput).toHaveValue("linear/scu-1-fix"));
  });

  // The one admission rule: a pi prompt is submittable only against a resolved,
  // non-empty catalog with a selection; a promptless create never waits on it.
  describe("pi model picker admission rule", () => {
    it("renders the pi model picker in place of the Claude controls", async () => {
      mockUsePiModels.mockReturnValue(piModelsPopulated());
      renderPiForm();

      await waitFor(() => expect(screen.getByTestId(ElementIds.NEW_WORKSPACE_CREATE_BUTTON)).toBeEnabled());
      expect(screen.getByTestId(ElementIds.NEW_WORKSPACE_PI_MODEL_PICKER)).toBeInTheDocument();
    });

    it("keeps a promptless pi create enabled while the catalog is still resolving", async () => {
      mockUsePiModels.mockReturnValue(piModelsResolving());
      renderPiForm();

      // No prompt → the create never waits on the catalog, even mid-probe.
      await waitFor(() => expect(screen.getByTestId(ElementIds.NEW_WORKSPACE_CREATE_BUTTON)).toBeEnabled());
    });

    it("blocks a pi prompt while the catalog is resolving, and re-enables when the prompt clears", async () => {
      mockUsePiModels.mockReturnValue(piModelsResolving());
      renderPiForm();

      const createButton = screen.getByTestId(ElementIds.NEW_WORKSPACE_CREATE_BUTTON);
      const promptTextarea = screen.getByTestId(ElementIds.NEW_WORKSPACE_PROMPT_TEXTAREA);
      // Promptless baseline: repo/branch are satisfied, so the only thing that can
      // disable the button from here is the pi admission gate.
      await waitFor(() => expect(createButton).toBeEnabled());

      fireEvent.change(promptTextarea, { target: { value: "do a thing" } });
      await waitFor(() => expect(createButton).toBeDisabled());

      fireEvent.change(promptTextarea, { target: { value: "" } });
      await waitFor(() => expect(createButton).toBeEnabled());
    });

    it("blocks a pi prompt when the catalog is empty and offers the login CTA", async () => {
      mockUsePiModels.mockReturnValue(piModelsEmpty());
      renderPiForm();

      const createButton = screen.getByTestId(ElementIds.NEW_WORKSPACE_CREATE_BUTTON);
      await waitFor(() => expect(createButton).toBeEnabled());

      fireEvent.change(screen.getByTestId(ElementIds.NEW_WORKSPACE_PROMPT_TEXTAREA), {
        target: { value: "do a thing" },
      });
      await waitFor(() => expect(createButton).toBeDisabled());
      // The no-usable-model surface routes the user to authenticate a provider.
      expect(screen.getByTestId(ElementIds.NEW_WORKSPACE_PI_EMPTY_STATE)).toBeInTheDocument();
    });

    it("routes the empty-state CTA to pi settings and dismisses the dialog", async () => {
      // The settings page opens underneath the host dialog, so the CTA must
      // also dismiss it — otherwise the modal keeps covering the page it opened.
      mockUsePiModels.mockReturnValue(piModelsEmpty());
      const onDismiss = vi.fn();
      renderPiForm({ onDismiss });

      fireEvent.change(screen.getByTestId(ElementIds.NEW_WORKSPACE_PROMPT_TEXTAREA), {
        target: { value: "do a thing" },
      });
      await waitFor(() => expect(screen.getByTestId(ElementIds.NEW_WORKSPACE_PI_EMPTY_STATE)).toBeInTheDocument());

      fireEvent.click(screen.getByTestId(ElementIds.NEW_WORKSPACE_PI_EMPTY_STATE));
      expect(mockOpenSettings).toHaveBeenCalledWith(SettingsSection.PI);
      expect(onDismiss).toHaveBeenCalledTimes(1);
    });

    it("enables a pi prompt against a populated catalog and creates with the default model preselected", async () => {
      mockUsePiModels.mockReturnValue(piModelsPopulated());
      renderPiForm();

      const createButton = screen.getByTestId(ElementIds.NEW_WORKSPACE_CREATE_BUTTON);
      await waitFor(() => expect(createButton).toBeEnabled());

      fireEvent.change(screen.getByTestId(ElementIds.NEW_WORKSPACE_PROMPT_TEXTAREA), {
        target: { value: "do a thing" },
      });
      // The default model is preselected, so the prompt stays submittable.
      await waitFor(() => expect(createButton).toBeEnabled());

      fireEvent.click(createButton);
      await waitFor(() =>
        expect(mockCreateWorkspace).toHaveBeenCalledWith(
          expect.objectContaining({ agentTypeValue: "pi", prompt: "do a thing", piBackendModel: PI_MODEL_DEFAULT }),
        ),
      );
    });
  });

  it("dismisses the dialog when Install Pi routes to settings from the agent picker", async () => {
    // With no usable pi binary, the picker's pi entry reads "Install Pi" and
    // routes to Settings — which lands underneath the host dialog, so choosing
    // it must dismiss the dialog exactly like the model picker's CTA.
    const onDismiss = vi.fn();
    const store = createStore();
    store.set(updateProjectsAtom, [{ objectId: "p1", name: "Repo One" } as Project]);
    store.set(dependenciesStatusAtom, {
      git: { installed: true },
      claude: { installed: false },
      pi: { installed: false },
      gh: { installed: false },
    } as DependenciesStatus);
    renderWithProviders(<NewWorkspaceForm onCreated={vi.fn()} onDismiss={onDismiss} />, { store });

    fireEvent.change(screen.getByTestId(ElementIds.NEW_WORKSPACE_PROMPT_TEXTAREA), {
      target: { value: "keep me" },
    });
    const user = userEvent.setup();
    await user.click(screen.getByTestId(ElementIds.ADD_WORKSPACE_AGENT_TYPE_SELECT));
    const piOption = await screen.findByTestId(ElementIds.AGENT_TYPE_OPTION_PI);
    expect(piOption).toHaveTextContent("Install Pi");
    await user.click(piOption);

    expect(mockOpenSettings).toHaveBeenCalledWith(SettingsSection.PI);
    expect(onDismiss).toHaveBeenCalledTimes(1);

    // The forced exit stashes the entries; the next open restores them.
    cleanup();
    renderWithProviders(<NewWorkspaceForm onCreated={vi.fn()} onDismiss={vi.fn()} />, { store });
    expect(screen.getByTestId(ElementIds.NEW_WORKSPACE_PROMPT_TEXTAREA)).toHaveValue("keep me");
  });

  it("restores the form's entries on the reopen after the empty-state CTA routed to settings", async () => {
    mockUsePiModels.mockReturnValue(piModelsEmpty());
    const store = createStore();
    store.set(updateProjectsAtom, [{ objectId: "p1", name: "Repo One" } as Project]);
    store.set(lastWorkspaceCreationSettingsAtom, {
      projectId: "p1",
      agentType: "pi",
      initStrategy: WorkspaceInitializationStrategy.WORKTREE,
    });
    renderWithProviders(<NewWorkspaceForm onCreated={vi.fn()} onDismiss={vi.fn()} />, { store });

    fireEvent.change(screen.getByTestId(ElementIds.WORKSPACE_NAME_INPUT), {
      target: { value: "My workspace" },
    });
    fireEvent.change(screen.getByTestId(ElementIds.NEW_WORKSPACE_PROMPT_TEXTAREA), {
      target: { value: "do a thing" },
    });
    await waitFor(() => expect(screen.getByTestId(ElementIds.NEW_WORKSPACE_PI_EMPTY_STATE)).toBeInTheDocument());
    fireEvent.click(screen.getByTestId(ElementIds.NEW_WORKSPACE_PI_EMPTY_STATE));

    // The authentication round-trip must not cost the user their entries.
    cleanup();
    renderWithProviders(<NewWorkspaceForm onCreated={vi.fn()} onDismiss={vi.fn()} />, { store });
    expect(screen.getByTestId(ElementIds.WORKSPACE_NAME_INPUT)).toHaveValue("My workspace");
    expect(screen.getByTestId(ElementIds.NEW_WORKSPACE_PROMPT_TEXTAREA)).toHaveValue("do a thing");

    // Dismissing the restored form re-stashes it: the entries survive until a
    // create consumes them.
    cleanup();
    renderWithProviders(<NewWorkspaceForm onCreated={vi.fn()} onDismiss={vi.fn()} />, { store });
    expect(screen.getByTestId(ElementIds.WORKSPACE_NAME_INPUT)).toHaveValue("My workspace");
    expect(screen.getByTestId(ElementIds.NEW_WORKSPACE_PROMPT_TEXTAREA)).toHaveValue("do a thing");
  });

  it("restores the form's entries after any dismissal — Escape and overlay clicks included", () => {
    // Every dismissal unmounts the form; the stash rides the unmount, so an
    // accidental Escape or stray overlay click costs nothing.
    const store = createStore();
    store.set(updateProjectsAtom, [{ objectId: "p1", name: "Repo One" } as Project]);
    renderWithProviders(<NewWorkspaceForm onCreated={vi.fn()} onDismiss={vi.fn()} />, { store });

    fireEvent.change(screen.getByTestId(ElementIds.WORKSPACE_NAME_INPUT), {
      target: { value: "Half-typed" },
    });
    fireEvent.change(screen.getByTestId(ElementIds.NEW_WORKSPACE_PROMPT_TEXTAREA), {
      target: { value: "an accidental escape" },
    });
    cleanup();

    renderWithProviders(<NewWorkspaceForm onCreated={vi.fn()} onDismiss={vi.fn()} />, { store });
    expect(screen.getByTestId(ElementIds.WORKSPACE_NAME_INPUT)).toHaveValue("Half-typed");
    expect(screen.getByTestId(ElementIds.NEW_WORKSPACE_PROMPT_TEXTAREA)).toHaveValue("an accidental escape");
  });

  it("clears the stash on a successful create so the next open starts fresh", async () => {
    const onCreated = vi.fn();
    const store = createStore();
    store.set(updateProjectsAtom, [{ objectId: "p1", name: "Repo One" } as Project]);
    renderWithProviders(<NewWorkspaceForm onCreated={onCreated} onDismiss={vi.fn()} />, { store });

    fireEvent.change(screen.getByTestId(ElementIds.WORKSPACE_NAME_INPUT), {
      target: { value: "Shipped" },
    });
    fireEvent.change(screen.getByTestId(ElementIds.NEW_WORKSPACE_PROMPT_TEXTAREA), {
      target: { value: "created, not drafted" },
    });
    await clickCreate();
    await waitFor(() => expect(onCreated).toHaveBeenCalled());
    cleanup();

    renderWithProviders(<NewWorkspaceForm onCreated={vi.fn()} onDismiss={vi.fn()} />, { store });
    expect(screen.getByTestId(ElementIds.WORKSPACE_NAME_INPUT)).toHaveValue("");
    expect(screen.getByTestId(ElementIds.NEW_WORKSPACE_PROMPT_TEXTAREA)).toHaveValue("");
  });

  it("lets an explicit open seed beat a stashed draft", () => {
    const store = createStore();
    store.set(updateProjectsAtom, [{ objectId: "p1", name: "Repo One" } as Project]);
    store.set(newWorkspaceDraftAtom, {
      projectId: "p1",
      title: "Draft title",
      prompt: "draft prompt",
      branchNameOverride: null,
      mode: WorkspaceInitializationStrategy.WORKTREE,
      sourceBranch: undefined,
      agentTypeValue: "claude",
      piSelectionOverride: undefined,
    });
    renderWithProviders(
      <NewWorkspaceForm
        initialTitle="Seeded title"
        initialPrompt="Seeded prompt"
        onCreated={vi.fn()}
        onDismiss={vi.fn()}
      />,
      { store },
    );

    expect(screen.getByTestId(ElementIds.WORKSPACE_NAME_INPUT)).toHaveValue("Seeded title");
    expect(screen.getByTestId(ElementIds.NEW_WORKSPACE_PROMPT_TEXTAREA)).toHaveValue("Seeded prompt");
  });
});
