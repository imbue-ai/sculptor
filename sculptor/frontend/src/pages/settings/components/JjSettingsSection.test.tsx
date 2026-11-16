import { act, cleanup, fireEvent, screen, within } from "@testing-library/react";
import { createStore } from "jotai";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { DependenciesStatus, DependencyInfo, JjReadiness, Project, UserConfig } from "~/api";
import { ElementIds, UserConfigField } from "~/api";
import { dependenciesStatusAtom } from "~/common/state/atoms/dependenciesStatus";
import { updateProjectsAtom } from "~/common/state/atoms/projects.ts";
import { userConfigAtom } from "~/common/state/atoms/userConfig.ts";
import { renderWithProviders } from "~/common/utils/renderWithProviders.tsx";

import { JjSettingsSection } from "./JjSettingsSection.tsx";

const { mockGetDependenciesStatus, mockSetJjIdentity } = vi.hoisted(() => ({
  mockGetDependenciesStatus: vi.fn(),
  mockSetJjIdentity: vi.fn(),
}));

vi.mock("~/api", async (importOriginal) => {
  const original = await importOriginal();
  return {
    ...(original as object),
    getDependenciesStatus: mockGetDependenciesStatus,
    setJjIdentity: mockSetJjIdentity,
  };
});

// Settings navigation is a route change; the repository links only need to ask for the right section.
const { mockOpenSettings } = vi.hoisted(() => ({ mockOpenSettings: vi.fn() }));
vi.mock("~/common/state/hooks/useOpenSettings.ts", () => ({
  useOpenSettings: (): unknown => mockOpenSettings,
}));

const makeInfo = (overrides: Partial<DependencyInfo>): DependencyInfo => ({ installed: false, ...overrides });

const makeStatus = (jjReadiness: JjReadiness): DependenciesStatus => ({
  git: makeInfo({ installed: true }),
  claude: makeInfo({ installed: true }),
  pi: makeInfo({}),
  gh: makeInfo({}),
  jj: makeInfo({ installed: true, isVersionInRange: true, mode: "MANAGED", version: "0.46.0" }),
  jjReadiness,
  voiceModels: makeInfo({}),
});

const IDENTITY = { name: "Ada Lovelace", email: "ada@example.com" };
const NO_IDENTITY = makeStatus({ blocker: "NO_IDENTITY", suggestedIdentity: IDENTITY });
const AVAILABLE = makeStatus({ blocker: null, identity: IDENTITY });
const NOT_INSTALLED = makeStatus({ blocker: "NOT_INSTALLED" });

type Deferred<T> = { promise: Promise<{ data: T }>; resolve: (value: T) => void };

const deferred = <T,>(): Deferred<T> => {
  let resolve: (value: T) => void = () => {};
  const promise = new Promise<{ data: T }>((settle) => {
    resolve = (value): void => settle({ data: value });
  });
  return { promise, resolve };
};

describe("JjSettingsSection", () => {
  let store: ReturnType<typeof createStore>;

  const renderSection = (): void => {
    renderWithProviders(<JjSettingsSection onSettingChange={vi.fn().mockResolvedValue(undefined)} />, { store });
  };

  beforeEach(() => {
    store = createStore();
    mockGetDependenciesStatus.mockResolvedValue({ data: NO_IDENTITY });
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("asks the backend to re-check on open, and keeps a newer stream frame when the response lands after it", async () => {
    store.set(dependenciesStatusAtom, NO_IDENTITY);
    const recheck = deferred<DependenciesStatus>();
    mockGetDependenciesStatus.mockReturnValueOnce(recheck.promise);
    renderSection();

    act(() => {
      store.set(dependenciesStatusAtom, AVAILABLE);
    });
    await act(async () => {
      recheck.resolve(NO_IDENTITY);
    });

    expect(mockGetDependenciesStatus).toHaveBeenCalledWith({ meta: { skipWsAck: true } });
    expect(store.get(dependenciesStatusAtom)).toBe(AVAILABLE);
  });

  it("re-checks when the user asks, leaving the status to the stream", async () => {
    store.set(dependenciesStatusAtom, NO_IDENTITY);
    renderSection();
    await act(async () => {});

    mockGetDependenciesStatus.mockResolvedValue({ data: AVAILABLE });
    await act(async () => {
      fireEvent.click(screen.getByTestId(ElementIds.JJ_RECHECK_BUTTON));
    });

    expect(mockGetDependenciesStatus).toHaveBeenCalledTimes(2);
    expect(store.get(dependenciesStatusAtom)).toBe(NO_IDENTITY);
    expect(screen.getByTestId(ElementIds.JJ_RECHECK_BUTTON)).toBeEnabled();
  });

  it("keeps a newer stream frame when the identity save responds after it", async () => {
    store.set(dependenciesStatusAtom, NO_IDENTITY);
    renderSection();
    await act(async () => {});
    const save = deferred<DependenciesStatus>();
    mockSetJjIdentity.mockReturnValueOnce(save.promise);

    fireEvent.click(screen.getByTestId(ElementIds.JJ_IDENTITY_SUBMIT));
    // The save published AVAILABLE, then jj went away before its response landed.
    act(() => {
      store.set(dependenciesStatusAtom, NOT_INSTALLED);
    });
    await act(async () => {
      save.resolve(AVAILABLE);
    });

    expect(mockSetJjIdentity).toHaveBeenCalledWith({ body: IDENTITY, meta: { skipWsAck: true } });
    expect(store.get(dependenciesStatusAtom)).toBe(NOT_INSTALLED);
  });

  describe("the repositories using jj", () => {
    it("lists each repository that uses jj for new workspaces, with a link to its settings", () => {
      store.set(updateProjectsAtom, [
        {
          objectId: "p1",
          name: "Alpha",
          userGitRepoUrl: "file:///repos/alpha",
          useJjForNewWorkspaces: true,
        } as Project,
        { objectId: "p2", name: "Beta", userGitRepoUrl: "file:///repos/beta", useJjForNewWorkspaces: false } as Project,
      ]);
      renderSection();

      const repositories = screen.getByTestId(ElementIds.JJ_REPOSITORIES);
      expect(within(repositories).getByText("Alpha")).toBeInTheDocument();
      expect(within(repositories).queryByText("Beta")).not.toBeInTheDocument();
      fireEvent.click(within(repositories).getByRole("link", { name: "Configure" }));

      expect(mockOpenSettings).toHaveBeenCalledWith("REPOSITORIES", "p1");
    });

    it("says where to turn jj on when no repository uses it", () => {
      store.set(updateProjectsAtom, [{ objectId: "p2", name: "Beta", useJjForNewWorkspaces: false } as Project]);
      renderSection();

      expect(screen.getByTestId(ElementIds.JJ_REPOSITORIES)).toHaveTextContent(
        "No repository uses jj for new workspaces yet.",
      );
    });
  });

  describe("the jj prompts", () => {
    const renderSectionSaving = (): ReturnType<typeof vi.fn> => {
      const onSettingChange = vi.fn().mockResolvedValue(undefined);
      renderWithProviders(<JjSettingsSection onSettingChange={onSettingChange} />, { store });
      return onSettingChange;
    };

    it("falls back to the git commit and PR prompts until set, and saves each as its own setting", () => {
      store.set(userConfigAtom, {
        commitPrompt: "Commit it all",
        prCreationPrompt: "Open a PR",
        jjCommitPrompt: null,
        jjPrCreationPrompt: "Push the bookmark and open a PR",
      } as UserConfig);
      const onSettingChange = renderSectionSaving();

      const commitRow = screen.getByTestId(ElementIds.JJ_COMMIT_PROMPT_SETTING);
      expect(within(commitRow).getByText("Commit it all")).toBeInTheDocument();
      fireEvent.click(within(commitRow).getByRole("button", { name: "Use suggested wording" }));
      const prRow = screen.getByTestId(ElementIds.JJ_PR_CREATION_PROMPT_SETTING);
      expect(within(prRow).getByRole("textbox")).toHaveValue("Push the bookmark and open a PR");
      fireEvent.click(within(prRow).getByRole("button", { name: "Use the git prompt" }));

      expect(onSettingChange).toHaveBeenCalledWith(UserConfigField.JJ_COMMIT_PROMPT, expect.stringContaining("jj"));
      expect(onSettingChange).toHaveBeenCalledWith(UserConfigField.JJ_PR_CREATION_PROMPT, null);
    });

    it("saves a jj CI babysitter prompt inside the babysitter's settings, keeping the rest", () => {
      const ciBabysitter = {
        enabled: true,
        retryCap: 3,
        pipelineFailedPrompt: "Fix the pipeline",
        mergeConflictPrompt: "Fix the conflict",
        jjPipelineFailedPrompt: null,
        jjMergeConflictPrompt: null,
      };
      store.set(userConfigAtom, { ciBabysitter } as unknown as UserConfig);
      const onSettingChange = renderSectionSaving();

      const pipelineRow = screen.getByTestId(ElementIds.JJ_CI_PIPELINE_FAILED_PROMPT_SETTING);
      expect(within(pipelineRow).getByText("Fix the pipeline")).toBeInTheDocument();
      fireEvent.click(within(pipelineRow).getByRole("button", { name: "Use suggested wording" }));

      expect(onSettingChange).toHaveBeenCalledWith(UserConfigField.CI_BABYSITTER, {
        ...ciBabysitter,
        jjPipelineFailedPrompt: expect.stringContaining("jj"),
      });
    });
  });
});
